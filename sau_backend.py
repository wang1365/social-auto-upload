import asyncio
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from queue import Queue

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

from conf import BASE_DIR
from myUtils.auth import check_cookie
from myUtils.login import (
    douyin_cookie_gen,
    get_ks_cookie,
    get_tencent_cookie,
    xiaohongshu_cookie_gen,
)
from myUtils.postVideo import (
    post_video_DouYin,
    post_video_ks,
    post_video_tencent,
    post_video_xhs,
)
from myUtils.translation import translate_title_to_zh
from myUtils.youtube_downloader import (
    classify_ytdlp_error,
    download_video,
    extract_video_metadata,
    is_playlist_url,
    is_valid_proxy_url,
    is_supported_youtube_url,
    sanitize_filename,
)


app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 160 * 1024 * 1024

active_queues = {}
youtube_tasks = {}
youtube_task_lock = threading.Lock()

CURRENT_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(BASE_DIR) / "db" / "database.db"
VIDEO_DIR = Path(BASE_DIR) / "videoFile"
COOKIE_DIR = Path(BASE_DIR) / "cookiesFile"
SYSTEM_COOKIE_DIR = COOKIE_DIR / "system"
ASSETS_DIR = CURRENT_DIR / "assets"


def db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_runtime_schema():
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    SYSTEM_COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type INTEGER NOT NULL,
                filePath TEXT NOT NULL,
                userName TEXT NOT NULL,
                status INTEGER DEFAULT 0
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS file_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                filesize REAL,
                upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                file_path TEXT
            )
            """
        )
        cursor.execute("PRAGMA table_info(file_records)")
        columns = {row["name"] for row in cursor.fetchall()}
        for column_name, column_type in [
            ("source_url", "TEXT"),
            ("source_type", "TEXT"),
            ("video_title", "TEXT"),
            ("video_title_zh", "TEXT"),
            ("video_description", "TEXT"),
        ]:
            if column_name not in columns:
                cursor.execute(f"ALTER TABLE file_records ADD COLUMN {column_name} {column_type}")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT
            )
            """
        )
        conn.commit()


def safe_relative_file(base_dir: Path, relative_path: str) -> Path:
    candidate = (base_dir / relative_path).resolve()
    if not candidate.is_relative_to(base_dir.resolve()):
        raise ValueError("Invalid file path")
    return candidate


def build_material_row(row):
    row_dict = dict(row)
    file_path = row_dict.get("file_path") or ""
    row_dict["uuid"] = file_path.split("_", 1)[0] if "_" in file_path else ""
    return row_dict


def generate_timestamp_filename() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def build_persisted_youtube_task(row):
    row_dict = dict(row)
    task_id = f"material-{row_dict['id']}"
    created_at = row_dict.get("upload_time")
    return {
        "task_id": task_id,
        "status": "success",
        "progress_text": "Download completed",
        "progress_percent": 100,
        "downloaded_bytes": None,
        "total_bytes": None,
        "speed_text": None,
        "eta_text": None,
        "phase": "completed",
        "material_id": row_dict["id"],
        "error_code": None,
        "error_message": None,
        "error_detail": None,
        "source_url": row_dict.get("source_url"),
        "video_id": None,
        "video_title": row_dict.get("video_title"),
        "video_title_zh": row_dict.get("video_title_zh"),
        "video_description": row_dict.get("video_description"),
        "filename": row_dict.get("filename"),
        "file_path": row_dict.get("file_path"),
        "created_at": created_at,
        "updated_at": created_at,
    }


def get_system_setting(setting_key: str, default_value: str = "") -> str:
    with db_connection() as conn:
        row = conn.execute(
            "SELECT setting_value FROM system_settings WHERE setting_key = ?",
            (setting_key,),
        ).fetchone()
    if not row:
        return default_value
    return row["setting_value"] or default_value


def set_system_setting(setting_key: str, setting_value: str) -> None:
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO system_settings (setting_key, setting_value)
            VALUES (?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value
            """,
            (setting_key, setting_value),
        )
        conn.commit()


def delete_system_setting(setting_key: str) -> None:
    with db_connection() as conn:
        conn.execute("DELETE FROM system_settings WHERE setting_key = ?", (setting_key,))
        conn.commit()


def get_youtube_cookie_path() -> Path | None:
    cookie_name = get_system_setting("youtube_cookie_file", "").strip()
    if not cookie_name:
        return None
    cookie_path = safe_relative_file(SYSTEM_COOKIE_DIR, cookie_name)
    if not cookie_path.exists():
        raise FileNotFoundError("configured YouTube cookie file does not exist")
    return cookie_path


def validate_netscape_cookie_file(file_storage) -> tuple[bool, str]:
    filename = (file_storage.filename or "").lower()
    if not filename.endswith(".txt"):
        return False, "YouTube cookie file must be a .txt file"

    stream = file_storage.stream
    current_pos = stream.tell()
    try:
        head = stream.read(4096)
        if isinstance(head, bytes):
            text = head.decode("utf-8-sig", errors="ignore")
        else:
            text = head
    finally:
        stream.seek(current_pos)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False, "Cookie file is empty"

    first_line = lines[0]
    has_header = first_line.startswith("# Netscape HTTP Cookie File")
    has_cookie_row = any(
        not line.startswith("#") and len(line.split("\t")) >= 6
        for line in lines
    )
    if not has_header and not has_cookie_row:
        return False, "Cookie file does not look like Netscape cookies.txt format"
    return True, ""


def create_material_record(
    filename,
    filepath,
    filesize_mb,
    source_url=None,
    source_type=None,
    video_title=None,
    video_title_zh=None,
    video_description=None,
):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO file_records (
                filename, filesize, file_path, source_url, source_type, video_title, video_title_zh, video_description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename,
                filesize_mb,
                filepath,
                source_url,
                source_type,
                video_title,
                video_title_zh,
                video_description,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def update_youtube_task(task_id, **kwargs):
    with youtube_task_lock:
        task = youtube_tasks.get(task_id)
        if task:
            task.update(kwargs)
            task["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def serialize_youtube_task(task):
    return {
        "taskId": task["task_id"],
        "status": task["status"],
        "progressText": task["progress_text"],
        "progressPercent": task.get("progress_percent"),
        "downloadedBytes": task.get("downloaded_bytes"),
        "totalBytes": task.get("total_bytes"),
        "speedText": task.get("speed_text"),
        "etaText": task.get("eta_text"),
        "phase": task.get("phase"),
        "materialId": task["material_id"],
        "errorCode": task["error_code"],
        "errorMessage": task["error_message"],
        "errorDetail": task["error_detail"],
        "sourceUrl": task.get("source_url"),
        "videoId": task.get("video_id"),
        "videoTitle": task.get("video_title"),
        "videoTitleZh": task.get("video_title_zh"),
        "videoDescription": task.get("video_description"),
        "filename": task.get("filename"),
        "filePath": task.get("file_path"),
        "createdAt": task.get("created_at"),
        "updatedAt": task.get("updated_at"),
    }


def format_download_progress(status):
    if status.get("status") == "downloading":
        parts = []
        percent = status.get("_percent_str", "").strip()
        speed = status.get("_speed_str", "").strip()
        eta = status.get("_eta_str", "").strip()
        if percent:
            parts.append(percent)
        if speed:
            parts.append(speed)
        if eta:
            parts.append(f"ETA {eta}")
        return " | ".join(parts) or "Downloading"
    if status.get("status") == "finished":
        return "Download finished, processing file"
    return "Pending"


def extract_progress_fields(status):
    percent_str = (status.get("_percent_str") or "").replace("%", "").strip()
    speed_text = (status.get("_speed_str") or "").strip() or None
    eta_text = (status.get("_eta_str") or "").strip() or None
    downloaded_bytes = status.get("downloaded_bytes")
    total_bytes = status.get("total_bytes") or status.get("total_bytes_estimate")
    progress_percent = None

    if percent_str:
        try:
            progress_percent = round(float(percent_str), 2)
        except ValueError:
            progress_percent = None

    return {
        "progress_percent": progress_percent,
        "downloaded_bytes": downloaded_bytes,
        "total_bytes": total_bytes,
        "speed_text": speed_text,
        "eta_text": eta_text,
    }


def process_youtube_download(task_id, url):
    try:
        proxy = get_system_setting("download_proxy", "").strip()
        if proxy and not is_valid_proxy_url(proxy):
            raise ValueError("proxy url is invalid")
        cookie_path = get_youtube_cookie_path()
        update_youtube_task(
            task_id,
            status="downloading",
            progress_text="Extracting metadata",
            phase="metadata",
            progress_percent=0,
            downloaded_bytes=None,
            total_bytes=None,
            speed_text=None,
            eta_text=None,
        )
        metadata = extract_video_metadata(
            url,
            proxy=proxy or None,
            cookiefile=str(cookie_path) if cookie_path else None,
        )
        try:
            translated_title = translate_title_to_zh(metadata.get("title") or "")
        except Exception:
            translated_title = ""
        update_youtube_task(
            task_id,
            video_id=metadata.get("id") or "",
            video_title=metadata.get("title") or "",
            video_title_zh=translated_title,
            video_description=metadata.get("description") or "",
            progress_text="Metadata extracted",
            phase="download",
            progress_percent=0,
        )
        filename_stem = f"{uuid.uuid4()}_{sanitize_filename(metadata.get('title') or 'youtube_video')}"

        def on_progress(status):
            progress_fields = extract_progress_fields(status)
            phase = "processing" if status.get("status") == "finished" else "download"
            update_youtube_task(
                task_id,
                status="downloading",
                phase=phase,
                progress_text=format_download_progress(status),
                **progress_fields,
            )

        final_path = download_video(
            url,
            VIDEO_DIR,
            filename_stem,
            on_progress,
            proxy=proxy or None,
            cookiefile=str(cookie_path) if cookie_path else None,
        )
        filesize_mb = round(final_path.stat().st_size / (1024 * 1024), 2)
        material_id = create_material_record(
            filename=final_path.name,
            filepath=final_path.name,
            filesize_mb=filesize_mb,
            source_url=url,
            source_type="youtube",
            video_title=metadata.get("title") or final_path.stem,
            video_title_zh=translated_title,
            video_description=metadata.get("description") or "",
        )
        update_youtube_task(
            task_id,
            status="success",
            progress_text="Download completed",
            phase="completed",
            progress_percent=100,
            material_id=material_id,
            filename=final_path.name,
            file_path=final_path.name,
            error_code=None,
            error_message=None,
            error_detail=None,
            speed_text=None,
            eta_text=None,
        )
    except Exception as exc:
        error_code, error_message, error_detail = classify_ytdlp_error(exc)
        update_youtube_task(
            task_id,
            status="failed",
            progress_text="Download failed",
            phase="failed",
            error_code=error_code,
            error_message=error_message,
            error_detail=error_detail,
        )


def run_async_function(platform_type, account_id, status_queue):
    if platform_type == "1":
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(xiaohongshu_cookie_gen(account_id, status_queue))
        loop.close()
    elif platform_type == "2":
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(get_tencent_cookie(account_id, status_queue))
        loop.close()
    elif platform_type == "3":
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(douyin_cookie_gen(account_id, status_queue))
        loop.close()
    elif platform_type == "4":
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(get_ks_cookie(account_id, status_queue))
        loop.close()


def sse_stream(status_queue):
    while True:
        if not status_queue.empty():
            msg = status_queue.get()
            yield f"data: {msg}\n\n"
        else:
            time.sleep(0.1)


ensure_runtime_schema()


@app.route("/assets/<filename>")
def custom_static(filename):
    return send_from_directory(str(ASSETS_DIR), filename)


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(str(ASSETS_DIR), "vite.svg")


@app.route("/vite.svg")
def vite_svg():
    return send_from_directory(str(ASSETS_DIR), "vite.svg")


@app.route("/")
def index():
    return send_from_directory(str(CURRENT_DIR), "index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"code": 400, "data": None, "msg": "No file part in the request"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"code": 400, "data": None, "msg": "No selected file"}), 400
    try:
        file_name = f"{uuid.uuid1()}_{file.filename}"
        filepath = VIDEO_DIR / file_name
        file.save(filepath)
        return jsonify({"code": 200, "msg": "File uploaded successfully", "data": file_name}), 200
    except Exception as exc:
        return jsonify({"code": 500, "msg": str(exc), "data": None}), 500


@app.route("/getFile", methods=["GET"])
def get_file():
    filename = request.args.get("filename")
    if not filename:
        return jsonify({"code": 400, "msg": "filename is required", "data": None}), 400
    if ".." in filename or filename.startswith("/"):
        return jsonify({"code": 400, "msg": "Invalid filename", "data": None}), 400
    return send_from_directory(str(VIDEO_DIR), filename)


@app.route("/download/<path:filename>", methods=["GET"])
def download_material_file(filename):
    if ".." in filename or filename.startswith("/"):
        return jsonify({"code": 400, "msg": "Invalid filename", "data": None}), 400
    return send_from_directory(str(VIDEO_DIR), filename, as_attachment=True)


@app.route("/uploadSave", methods=["POST"])
def upload_save():
    if "file" not in request.files:
        return jsonify({"code": 400, "data": None, "msg": "No file part in the request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"code": 400, "data": None, "msg": "No selected file"}), 400

    custom_filename = request.form.get("filename")
    filename = custom_filename + "." + file.filename.split(".")[-1] if custom_filename else file.filename

    try:
        final_filename = f"{uuid.uuid1()}_{filename}"
        filepath = VIDEO_DIR / final_filename
        file.save(filepath)
        create_material_record(
            filename=filename,
            filepath=final_filename,
            filesize_mb=round(float(os.path.getsize(filepath)) / (1024 * 1024), 2),
        )
        return jsonify({
            "code": 200,
            "msg": "File uploaded and saved successfully",
            "data": {"filename": filename, "filepath": final_filename},
        }), 200
    except Exception as exc:
        return jsonify({"code": 500, "msg": f"upload failed: {exc}", "data": None}), 500


@app.route("/youtube/download", methods=["POST"])
def youtube_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"code": 400, "msg": "Video URL is required", "data": None}), 400
    if not is_supported_youtube_url(url):
        return jsonify({"code": 400, "msg": "Only single YouTube video URLs are supported", "data": None}), 400
    if is_playlist_url(url):
        return jsonify({"code": 400, "msg": "Playlist URLs are not supported", "data": None}), 400

    task_id = uuid.uuid4().hex
    with youtube_task_lock:
        youtube_tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "progress_text": "Task created",
            "progress_percent": 0,
            "downloaded_bytes": None,
            "total_bytes": None,
            "speed_text": None,
            "eta_text": None,
            "phase": "pending",
            "material_id": None,
            "error_code": None,
            "error_message": None,
            "error_detail": None,
            "source_url": url,
            "video_id": None,
            "video_title": None,
            "video_title_zh": None,
            "video_description": None,
            "filename": None,
            "file_path": None,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    thread = threading.Thread(target=process_youtube_download, args=(task_id, url), daemon=True)
    thread.start()
    return jsonify({"code": 200, "msg": "success", "data": {"taskId": task_id}}), 200


@app.route("/youtube/task", methods=["GET"])
def youtube_task():
    task_id = request.args.get("taskId", "").strip()
    if not task_id:
        return jsonify({"code": 400, "msg": "taskId is required", "data": None}), 400
    with youtube_task_lock:
        task = youtube_tasks.get(task_id)
        if not task:
            return jsonify({"code": 404, "msg": "Task not found", "data": None}), 404
        payload = serialize_youtube_task(dict(task))
    return jsonify({"code": 200, "msg": "success", "data": payload}), 200


@app.route("/youtube/tasks", methods=["GET"])
def youtube_task_list():
    with youtube_task_lock:
        tasks = [serialize_youtube_task(dict(task)) for task in youtube_tasks.values()]
    tasks.sort(key=lambda item: (item.get("createdAt") or "", item.get("taskId") or ""), reverse=True)
    return jsonify({"code": 200, "msg": "success", "data": tasks}), 200


@app.route("/system/settings", methods=["GET"])
def get_system_settings():
    youtube_cookie_file = get_system_setting("youtube_cookie_file", "").strip()
    return jsonify({
        "code": 200,
        "msg": "success",
        "data": {
            "downloadProxy": get_system_setting("download_proxy", ""),
            "youtubeCookieFileName": youtube_cookie_file,
            "youtubeCookieConfigured": bool(youtube_cookie_file),
        },
    }), 200


@app.route("/system/settings", methods=["POST"])
def update_system_settings():
    data = request.get_json(silent=True) or {}
    download_proxy = (data.get("downloadProxy") or "").strip()
    if download_proxy and not is_valid_proxy_url(download_proxy):
        return jsonify({
            "code": 400,
            "msg": "downloadProxy must be a valid http/https/socks5 proxy URL",
            "data": None,
        }), 400
    set_system_setting("download_proxy", download_proxy)
    return jsonify({
        "code": 200,
        "msg": "Settings saved",
        "data": {
            "downloadProxy": download_proxy,
            "youtubeCookieFileName": get_system_setting("youtube_cookie_file", "").strip(),
            "youtubeCookieConfigured": bool(get_system_setting("youtube_cookie_file", "").strip()),
        },
    }), 200


@app.route("/system/settings/youtube-cookie", methods=["POST"])
def upload_youtube_cookie():
    if "file" not in request.files:
        return jsonify({"code": 400, "msg": "YouTube cookie file is required", "data": None}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"code": 400, "msg": "YouTube cookie filename is required", "data": None}), 400

    is_valid, error_message = validate_netscape_cookie_file(file)
    if not is_valid:
        return jsonify({"code": 400, "msg": error_message, "data": None}), 400

    target_name = "youtube_cookies.txt"
    target_path = SYSTEM_COOKIE_DIR / target_name
    try:
        file.save(target_path)
        set_system_setting("youtube_cookie_file", target_name)
        return jsonify({
            "code": 200,
            "msg": "YouTube cookie uploaded successfully",
            "data": {
                "youtubeCookieFileName": target_name,
                "youtubeCookieConfigured": True,
            },
        }), 200
    except Exception as exc:
        return jsonify({"code": 500, "msg": f"Upload YouTube cookie failed: {exc}", "data": None}), 500


@app.route("/system/settings/youtube-cookie", methods=["DELETE"])
def delete_youtube_cookie():
    cookie_name = get_system_setting("youtube_cookie_file", "").strip()
    if cookie_name:
        cookie_path = safe_relative_file(SYSTEM_COOKIE_DIR, cookie_name)
        if cookie_path.exists():
            cookie_path.unlink()
    delete_system_setting("youtube_cookie_file")
    return jsonify({
        "code": 200,
        "msg": "YouTube cookie cleared",
        "data": {
            "youtubeCookieFileName": "",
            "youtubeCookieConfigured": False,
        },
    }), 200


@app.route("/getFiles", methods=["GET"])
def get_all_files():
    try:
        with db_connection() as conn:
            rows = conn.execute("SELECT * FROM file_records ORDER BY upload_time DESC, id DESC").fetchall()
        data = [build_material_row(row) for row in rows]
        return jsonify({"code": 200, "msg": "success", "data": data}), 200
    except Exception:
        return jsonify({"code": 500, "msg": "get file failed!", "data": None}), 500


@app.route("/getAccounts", methods=["GET"])
def get_accounts():
    try:
        with db_connection() as conn:
            rows = conn.execute("SELECT * FROM user_info").fetchall()
        rows_list = [list(row) for row in rows]
        return jsonify({"code": 200, "msg": None, "data": rows_list}), 200
    except Exception as exc:
        return jsonify({"code": 500, "msg": f"Get accounts failed: {exc}", "data": None}), 500


@app.route("/getValidAccounts", methods=["GET"])
async def get_valid_accounts():
    with db_connection() as conn:
        rows = conn.execute("SELECT * FROM user_info").fetchall()
        rows_list = [list(row) for row in rows]
        for row in rows_list:
            flag = await check_cookie(row[1], row[2])
            if not flag:
                row[4] = 0
                conn.execute("UPDATE user_info SET status = ? WHERE id = ?", (0, row[0]))
        conn.commit()
    return jsonify({"code": 200, "msg": None, "data": rows_list}), 200


@app.route("/deleteFile", methods=["GET"])
def delete_file():
    file_id = request.args.get("id")
    if not file_id or not file_id.isdigit():
        return jsonify({"code": 400, "msg": "Invalid or missing file ID", "data": None}), 400

    try:
        with db_connection() as conn:
            record = conn.execute("SELECT * FROM file_records WHERE id = ?", (file_id,)).fetchone()
            if not record:
                return jsonify({"code": 404, "msg": "File not found", "data": None}), 404
            record = dict(record)
            file_path = VIDEO_DIR / record["file_path"]
            if file_path.exists():
                file_path.unlink()
            conn.execute("DELETE FROM file_records WHERE id = ?", (file_id,))
            conn.commit()
        return jsonify({
            "code": 200,
            "msg": "File deleted successfully",
            "data": {"id": record["id"], "filename": record["filename"]},
        }), 200
    except Exception:
        return jsonify({"code": 500, "msg": "delete failed!", "data": None}), 500


@app.route("/deleteAccount", methods=["GET"])
def delete_account():
    account_id = request.args.get("id")
    if not account_id or not account_id.isdigit():
        return jsonify({"code": 400, "msg": "Invalid or missing account ID", "data": None}), 400

    try:
        with db_connection() as conn:
            record = conn.execute("SELECT * FROM user_info WHERE id = ?", (int(account_id),)).fetchone()
            if not record:
                return jsonify({"code": 404, "msg": "account not found", "data": None}), 404
            record = dict(record)
            if record.get("filePath"):
                cookie_file_path = COOKIE_DIR / record["filePath"]
                if cookie_file_path.exists():
                    cookie_file_path.unlink()
            conn.execute("DELETE FROM user_info WHERE id = ?", (int(account_id),))
            conn.commit()
        return jsonify({"code": 200, "msg": "account deleted successfully", "data": None}), 200
    except Exception as exc:
        return jsonify({"code": 500, "msg": f"delete failed: {exc}", "data": None}), 500


@app.route("/login")
def login():
    platform_type = request.args.get("type")
    account_id = request.args.get("id")
    status_queue = Queue()
    active_queues[account_id] = status_queue
    thread = threading.Thread(target=run_async_function, args=(platform_type, account_id, status_queue), daemon=True)
    thread.start()
    response = Response(sse_stream(status_queue), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Content-Type"] = "text/event-stream"
    response.headers["Connection"] = "keep-alive"
    return response


@app.route("/postVideo", methods=["POST"])
def post_video():
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "Request data is required", "data": None}), 400

    file_list = data.get("fileList", [])
    account_list = data.get("accountList", [])
    platform_type = data.get("type")
    title = data.get("title")
    tags = data.get("tags")
    category = data.get("category")
    enable_timer = data.get("enableTimer")
    if category == 0:
        category = None
    product_link = data.get("productLink", "")
    product_title = data.get("productTitle", "")
    thumbnail_path = data.get("thumbnail", "")
    is_draft = data.get("isDraft", False)
    videos_per_day = data.get("videosPerDay")
    daily_times = data.get("dailyTimes")
    start_days = data.get("startDays")

    if not file_list:
        return jsonify({"code": 400, "msg": "fileList is required", "data": None}), 400
    if not account_list:
        return jsonify({"code": 400, "msg": "accountList is required", "data": None}), 400
    if not platform_type:
        return jsonify({"code": 400, "msg": "type is required", "data": None}), 400
    if not title:
        return jsonify({"code": 400, "msg": "title is required", "data": None}), 400

    try:
        match platform_type:
            case 1:
                post_video_xhs(title, file_list, tags, account_list, category, enable_timer, videos_per_day, daily_times, start_days)
            case 2:
                post_video_tencent(title, file_list, tags, account_list, category, enable_timer, videos_per_day, daily_times, start_days, is_draft)
            case 3:
                post_video_DouYin(title, file_list, tags, account_list, category, enable_timer, videos_per_day, daily_times, start_days, thumbnail_path, product_link, product_title)
            case 4:
                post_video_ks(title, file_list, tags, account_list, category, enable_timer, videos_per_day, daily_times, start_days)
            case _:
                return jsonify({"code": 400, "msg": f"Unsupported platform type: {platform_type}", "data": None}), 400
        return jsonify({"code": 200, "msg": "Publish task submitted", "data": None}), 200
    except Exception as exc:
        return jsonify({"code": 500, "msg": f"Publish failed: {exc}", "data": None}), 500


@app.route("/updateUserinfo", methods=["POST"])
def update_userinfo():
    data = request.get_json() or {}
    user_id = data.get("id")
    platform_type = data.get("type")
    username = data.get("userName")
    try:
        with db_connection() as conn:
            conn.execute(
                """
                UPDATE user_info
                SET type = ?, userName = ?
                WHERE id = ?
                """,
                (platform_type, username, user_id),
            )
            conn.commit()
        return jsonify({"code": 200, "msg": "account update successfully", "data": None}), 200
    except Exception:
        return jsonify({"code": 500, "msg": "update failed!", "data": None}), 500


@app.route("/postVideoBatch", methods=["POST"])
def post_video_batch():
    data_list = request.get_json()
    if not isinstance(data_list, list):
        return jsonify({"code": 400, "msg": "Expected a JSON array", "data": None}), 400

    for data in data_list:
        file_list = data.get("fileList", [])
        account_list = data.get("accountList", [])
        platform_type = data.get("type")
        title = data.get("title")
        tags = data.get("tags")
        category = data.get("category")
        enable_timer = data.get("enableTimer")
        if category == 0:
            category = None
        product_link = data.get("productLink", "")
        product_title = data.get("productTitle", "")
        is_draft = data.get("isDraft", False)
        videos_per_day = data.get("videosPerDay")
        daily_times = data.get("dailyTimes")
        start_days = data.get("startDays")

        match platform_type:
            case 1:
                post_video_xhs(title, file_list, tags, account_list, category, enable_timer, videos_per_day, daily_times, start_days)
            case 2:
                post_video_tencent(title, file_list, tags, account_list, category, enable_timer, videos_per_day, daily_times, start_days, is_draft)
            case 3:
                post_video_DouYin(title, file_list, tags, account_list, category, enable_timer, videos_per_day, daily_times, start_days, product_link, product_title)
            case 4:
                post_video_ks(title, file_list, tags, account_list, category, enable_timer, videos_per_day, daily_times, start_days)

    return jsonify({"code": 200, "msg": None, "data": None}), 200


@app.route("/uploadCookie", methods=["POST"])
def upload_cookie():
    try:
        if "file" not in request.files:
            return jsonify({"code": 400, "msg": "Cookie file is required", "data": None}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"code": 400, "msg": "Cookie filename is required", "data": None}), 400
        if not file.filename.endswith(".json"):
            return jsonify({"code": 400, "msg": "Cookie file must be JSON", "data": None}), 400

        account_id = request.form.get("id")
        platform = request.form.get("platform")
        if not account_id or not platform:
            return jsonify({"code": 400, "msg": "Account id and platform are required", "data": None}), 400

        with db_connection() as conn:
            result = conn.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,)).fetchone()
        if not result:
            return jsonify({"code": 404, "msg": "Account not found", "data": None}), 404

        cookie_file_path = COOKIE_DIR / result["filePath"]
        cookie_file_path.parent.mkdir(parents=True, exist_ok=True)
        file.save(str(cookie_file_path))
        return jsonify({"code": 200, "msg": "Cookie uploaded successfully", "data": None}), 200
    except Exception as exc:
        return jsonify({"code": 500, "msg": f"Upload cookie failed: {exc}", "data": None}), 500


@app.route("/downloadCookie", methods=["GET"])
def download_cookie():
    try:
        file_path = request.args.get("filePath")
        if not file_path:
            return jsonify({"code": 400, "msg": "filePath is required", "data": None}), 400
        cookie_file_path = safe_relative_file(COOKIE_DIR, file_path)
        if not cookie_file_path.exists():
            return jsonify({"code": 404, "msg": "Cookie file not found", "data": None}), 404
        return send_from_directory(str(cookie_file_path.parent), cookie_file_path.name, as_attachment=True)
    except ValueError as exc:
        return jsonify({"code": 400, "msg": str(exc), "data": None}), 400
    except Exception as exc:
        return jsonify({"code": 500, "msg": f"Download cookie failed: {exc}", "data": None}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5409)
