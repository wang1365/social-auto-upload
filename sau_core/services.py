from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Callable, Iterable

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
from myUtils.translation import translate_subtitle_file_to_zh, translate_title_to_zh
from myUtils.youtube_downloader import (
    classify_ytdlp_error,
    download_video,
    embed_subtitle_into_video,
    extract_video_metadata,
    is_playlist_url,
    is_supported_youtube_url,
    is_valid_proxy_url,
    sanitize_filename,
)
from myUtils.video_processor import (
    load_video_processing_config,
    normalize_video_processing_config,
    probe_video,
    process_video,
)


DATABASE_PATH = Path(BASE_DIR) / "db" / "database.db"
VIDEO_DIR = Path(BASE_DIR) / "videoFile"
COOKIE_DIR = Path(BASE_DIR) / "cookiesFile"
SYSTEM_COOKIE_DIR = COOKIE_DIR / "system"

ProgressCallback = Callable[[dict], None]

PLATFORM_CHOICES = [(1, "小红书"), (2, "视频号"), (3, "抖音"), (4, "快手")]


class ServiceError(RuntimeError):
    def __init__(self, message: str, code: str = "service_error"):
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class RuntimePaths:
    database_path: Path = DATABASE_PATH
    video_dir: Path = VIDEO_DIR
    cookie_dir: Path = COOKIE_DIR
    system_cookie_dir: Path = SYSTEM_COOKIE_DIR


def db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_runtime_schema() -> None:
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
            ("subtitle_path", "TEXT"),
            ("material_type", "TEXT DEFAULT 'original'"),
            ("parent_file_id", "INTEGER"),
            ("display_tags", "TEXT"),
            ("processing_profile", "TEXT"),
            ("processing_config", "TEXT"),
            ("video_resolution", "TEXT"),
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
        raise ServiceError("Invalid file path", "invalid_path")
    return candidate


def build_material_row(row) -> dict:
    row_dict = dict(row)
    file_path = row_dict.get("file_path") or ""
    row_dict["uuid"] = file_path.split("_", 1)[0] if "_" in file_path else ""
    tags = row_dict.get("display_tags") or "[]"
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except ValueError:
            tags = []
    row_dict["display_tags"] = tags if isinstance(tags, list) else []
    row_dict["material_type"] = row_dict.get("material_type") or "original"
    return row_dict


def create_material_record(
    filename,
    filepath,
    filesize_mb,
    source_url=None,
    source_type=None,
    video_title=None,
    video_title_zh=None,
    video_description=None,
    subtitle_path=None,
    material_type="original",
    parent_file_id=None,
    display_tags=None,
    processing_profile=None,
    processing_config=None,
    video_resolution=None,
):
    if isinstance(display_tags, list):
        display_tags_value = json.dumps(display_tags, ensure_ascii=False)
    elif display_tags:
        display_tags_value = str(display_tags)
    else:
        display_tags_value = None

    if isinstance(processing_config, dict):
        processing_config_value = json.dumps(processing_config, ensure_ascii=False)
    elif processing_config:
        processing_config_value = str(processing_config)
    else:
        processing_config_value = None

    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO file_records (
                filename, filesize, file_path, source_url, source_type, video_title, video_title_zh,
                video_description, subtitle_path, material_type, parent_file_id, display_tags,
                processing_profile, processing_config, video_resolution
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                subtitle_path,
                material_type,
                parent_file_id,
                display_tags_value,
                processing_profile,
                processing_config_value,
                video_resolution,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def delete_material_record(conn, file_id: int):
    record = conn.execute("SELECT * FROM file_records WHERE id = ?", (file_id,)).fetchone()
    if not record:
        return None

    record = dict(record)
    for key in ("file_path", "subtitle_path"):
        relative_path = record.get(key) or ""
        if relative_path:
            file_path = safe_relative_file(VIDEO_DIR, relative_path)
            if file_path.exists():
                file_path.unlink()

    conn.execute("DELETE FROM file_records WHERE id = ?", (file_id,))
    return {"id": record["id"], "filename": record["filename"]}


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


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


def get_video_processing_settings() -> dict:
    raw_value = get_system_setting("video_processing_config", "")
    return load_video_processing_config(raw_value)


def save_video_processing_settings(config: dict) -> dict:
    normalized_config = normalize_video_processing_config(config)
    set_system_setting("video_processing_config", json.dumps(normalized_config, ensure_ascii=False))
    return normalized_config


def get_youtube_cookie_path() -> Path | None:
    cookie_name = get_system_setting("youtube_cookie_file", "").strip()
    if not cookie_name:
        return None
    cookie_path = safe_relative_file(SYSTEM_COOKIE_DIR, cookie_name)
    if not cookie_path.exists():
        raise ServiceError("configured YouTube cookie file does not exist", "missing_cookie")
    return cookie_path


def validate_netscape_cookie_text(filename: str, data: bytes) -> None:
    if not filename.lower().endswith(".txt"):
        raise ServiceError("YouTube cookie file must be a .txt file", "invalid_cookie")
    text = data[:4096].decode("utf-8-sig", errors="ignore")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ServiceError("Cookie file is empty", "invalid_cookie")
    has_header = lines[0].startswith("# Netscape HTTP Cookie File")
    has_cookie_row = any(not line.startswith("#") and len(line.split("\t")) >= 6 for line in lines)
    if not has_header and not has_cookie_row:
        raise ServiceError("Cookie file does not look like Netscape cookies.txt format", "invalid_cookie")


def read_subtitle_text(relative_path: str | None) -> str:
    if not relative_path:
        return ""
    try:
        subtitle_path = safe_relative_file(VIDEO_DIR, relative_path)
    except ServiceError:
        return ""
    if not subtitle_path.exists() or not subtitle_path.is_file():
        return ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return subtitle_path.read_text(encoding=encoding).strip()
        except UnicodeDecodeError:
            continue
        except OSError:
            return ""
    return ""


def detect_video_resolution(relative_path: str | None) -> str:
    if not relative_path:
        return ""
    try:
        metadata = probe_video(safe_relative_file(VIDEO_DIR, relative_path))
    except Exception:
        return ""
    width = metadata.get("width")
    height = metadata.get("height")
    if width and height:
        return f"{int(width)}x{int(height)}"
    return ""


class SettingsService:
    def get_settings(self) -> dict:
        youtube_cookie_file = get_system_setting("youtube_cookie_file", "").strip()
        return {
            "downloadProxy": get_system_setting("download_proxy", ""),
            "youtubeCookieFileName": youtube_cookie_file,
            "youtubeCookieConfigured": bool(youtube_cookie_file),
            "videoProcessing": get_video_processing_settings(),
        }

    def save_settings(self, download_proxy: str = "", video_processing: dict | None = None) -> dict:
        download_proxy = (download_proxy or "").strip()
        if download_proxy and not is_valid_proxy_url(download_proxy):
            raise ServiceError(
                "downloadProxy must be a valid http/https/socks5 proxy URL",
                "invalid_proxy",
            )
        set_system_setting("download_proxy", download_proxy)
        if video_processing is not None:
            save_video_processing_settings(video_processing)
        return self.get_settings()

    def upload_youtube_cookie(self, source_path: Path) -> dict:
        source_path = Path(source_path)
        data = source_path.read_bytes()
        validate_netscape_cookie_text(source_path.name, data)
        SYSTEM_COOKIE_DIR.mkdir(parents=True, exist_ok=True)
        target_name = "youtube_cookies.txt"
        (SYSTEM_COOKIE_DIR / target_name).write_bytes(data)
        set_system_setting("youtube_cookie_file", target_name)
        return self.get_settings()

    def clear_youtube_cookie(self) -> dict:
        cookie_name = get_system_setting("youtube_cookie_file", "").strip()
        if cookie_name:
            cookie_path = safe_relative_file(SYSTEM_COOKIE_DIR, cookie_name)
            if cookie_path.exists():
                cookie_path.unlink()
        delete_system_setting("youtube_cookie_file")
        return self.get_settings()


class MaterialService:
    def list_materials(self) -> list[dict]:
        with db_connection() as conn:
            rows = conn.execute("SELECT * FROM file_records ORDER BY upload_time DESC, id DESC").fetchall()
        return [build_material_row(row) for row in rows]

    def import_files(self, paths: Iterable[Path], custom_filename: str = "") -> list[dict]:
        imported = []
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        paths = [Path(path) for path in paths]
        for index, source_path in enumerate(paths):
            if not source_path.exists() or not source_path.is_file():
                raise ServiceError(f"File not found: {source_path}", "missing_file")
            display_name = source_path.name
            if custom_filename and len(paths) == 1:
                display_name = f"{custom_filename}{source_path.suffix}"
            stored_name = f"{uuid.uuid1()}_{display_name}"
            target_path = VIDEO_DIR / stored_name
            shutil.copy2(source_path, target_path)
            material_id = create_material_record(
                filename=display_name,
                filepath=stored_name,
                filesize_mb=round(target_path.stat().st_size / (1024 * 1024), 2),
            )
            imported.append({"id": material_id, "filename": display_name, "file_path": stored_name, "index": index})
        return imported

    def delete_material(self, material_id: int) -> dict:
        with db_connection() as conn:
            deleted = delete_material_record(conn, int(material_id))
            if not deleted:
                raise ServiceError("File not found", "not_found")
            conn.commit()
        return deleted

    def delete_materials(self, material_ids: Iterable[int]) -> dict:
        deleted_items = []
        missing_ids = []
        with db_connection() as conn:
            for material_id in dict.fromkeys(int(item) for item in material_ids):
                deleted = delete_material_record(conn, material_id)
                if deleted:
                    deleted_items.append(deleted)
                else:
                    missing_ids.append(material_id)
            conn.commit()
        return {"deleted": deleted_items, "missingIds": missing_ids}

    def resolve_material_path(self, relative_path: str) -> Path:
        return safe_relative_file(VIDEO_DIR, relative_path)


class AccountService:
    PLATFORM_NAMES = {1: "小红书", 2: "视频号", 3: "抖音", 4: "快手"}

    def list_accounts(self) -> list[dict]:
        with db_connection() as conn:
            rows = conn.execute("SELECT * FROM user_info ORDER BY id DESC").fetchall()
        return [self._row_to_account(row) for row in rows]

    async def list_validated_accounts(self) -> list[dict]:
        with db_connection() as conn:
            rows = conn.execute("SELECT * FROM user_info ORDER BY id DESC").fetchall()
            accounts = []
            for row in rows:
                account = self._row_to_account(row)
                if not await check_cookie(account["type"], account["filePath"]):
                    account["status"] = 0
                    conn.execute("UPDATE user_info SET status = ? WHERE id = ?", (0, account["id"]))
                accounts.append(account)
            conn.commit()
        return accounts

    def update_account(self, account_id: int, platform_type: int, username: str) -> None:
        with db_connection() as conn:
            conn.execute(
                "UPDATE user_info SET type = ?, userName = ? WHERE id = ?",
                (platform_type, username, account_id),
            )
            conn.commit()

    def delete_account(self, account_id: int) -> None:
        with db_connection() as conn:
            record = conn.execute("SELECT * FROM user_info WHERE id = ?", (int(account_id),)).fetchone()
            if not record:
                raise ServiceError("account not found", "not_found")
            record = dict(record)
            if record.get("filePath"):
                cookie_file_path = safe_relative_file(COOKIE_DIR, record["filePath"])
                if cookie_file_path.exists():
                    cookie_file_path.unlink()
            conn.execute("DELETE FROM user_info WHERE id = ?", (int(account_id),))
            conn.commit()

    def import_cookie(self, account_id: int, source_path: Path) -> None:
        source_path = Path(source_path)
        if source_path.suffix.lower() != ".json":
            raise ServiceError("Cookie file must be JSON", "invalid_cookie")
        with db_connection() as conn:
            row = conn.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,)).fetchone()
        if not row:
            raise ServiceError("Account not found", "not_found")
        cookie_file_path = safe_relative_file(COOKIE_DIR, row["filePath"])
        cookie_file_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, cookie_file_path)

    def export_cookie_path(self, file_path: str) -> Path:
        cookie_file_path = safe_relative_file(COOKIE_DIR, file_path)
        if not cookie_file_path.exists():
            raise ServiceError("Cookie file not found", "not_found")
        return cookie_file_path

    def start_login(self, platform_type: int, account_id: str, callback: ProgressCallback | None = None) -> threading.Thread:
        def runner():
            queue: Queue = Queue()

            def pump():
                while True:
                    message = queue.get()
                    if callback:
                        callback({"type": "login", "message": message})
                    if message in {"200", "500"}:
                        break

            pump_thread = threading.Thread(target=pump, daemon=True)
            pump_thread.start()
            asyncio.run(_run_login(platform_type, account_id, queue))

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        return thread

    def _row_to_account(self, row) -> dict:
        data = dict(row)
        data["platform"] = self.PLATFORM_NAMES.get(data.get("type"), str(data.get("type")))
        return data


async def _run_login(platform_type, account_id, status_queue):
    if str(platform_type) == "1":
        await xiaohongshu_cookie_gen(account_id, status_queue)
    elif str(platform_type) == "2":
        await get_tencent_cookie(account_id, status_queue)
    elif str(platform_type) == "3":
        await douyin_cookie_gen(account_id, status_queue)
    elif str(platform_type) == "4":
        await get_ks_cookie(account_id, status_queue)
    else:
        status_queue.put("500")


class ProcessingService:
    def __init__(self):
        self.tasks: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.condition = threading.Condition()
        self.active_count = 0

    def get_settings(self) -> dict:
        return get_video_processing_settings()

    def save_settings(self, config: dict) -> dict:
        return save_video_processing_settings(config)

    def list_tasks(self) -> list[dict]:
        with self.lock:
            tasks = [self._serialize_task(dict(task)) for task in self.tasks.values()]
        return sorted(tasks, key=lambda item: (item.get("createdAt") or "", item.get("taskId") or ""), reverse=True)

    def get_task(self, task_id: str) -> dict:
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                raise ServiceError("Task not found", "not_found")
            return self._serialize_task(dict(task))

    def create_task(
        self,
        source_material_id: int,
        source_path: str,
        source_filename: str,
        callback: ProgressCallback | None = None,
    ) -> str:
        config = self.get_settings()
        task_id = uuid.uuid4().hex
        with self.lock:
            self.tasks[task_id] = {
                "task_id": task_id,
                "status": "pending",
                "progress_text": "等待处理",
                "progress_percent": 0,
                "source_material_id": source_material_id,
                "processed_material_id": None,
                "source_filename": source_filename,
                "processed_filename": None,
                "source_file_path": source_path,
                "processed_file_path": None,
                "error_message": None,
                "error_detail": None,
                "config": config,
                "created_at": _now(),
                "updated_at": _now(),
            }
        threading.Thread(target=self._process_task, args=(task_id, callback), daemon=True).start()
        return task_id

    def _process_task(self, task_id: str, callback: ProgressCallback | None) -> None:
        task = self.tasks[task_id]
        self._update_task(task_id, status="running", progress_text="正在处理视频", progress_percent=5)
        self._emit(callback, self.get_task(task_id))
        try:
            self._acquire_slot()
            source_path = safe_relative_file(VIDEO_DIR, task["source_file_path"])
            output_filename = f"{Path(task['source_filename']).stem}.processed.{datetime.now():%Y%m%d%H%M%S}.mp4"
            output_relative = f"{uuid.uuid1()}_{output_filename}"
            output_path = VIDEO_DIR / output_relative

            def on_progress(percent, text):
                self._update_task(task_id, progress_percent=percent, progress_text=text)
                self._emit(callback, self.get_task(task_id))

            result = process_video(source_path, output_path, task["config"], progress_callback=on_progress)
            material_id = create_material_record(
                filename=output_filename,
                filepath=output_relative,
                filesize_mb=round(output_path.stat().st_size / (1024 * 1024), 2),
                source_type="processed",
                material_type="processed",
                parent_file_id=task["source_material_id"],
                display_tags=["已处理", "视频处理"],
                processing_profile=result.get("profile"),
                processing_config=result.get("config"),
            )
            self._update_task(
                task_id,
                status="success",
                progress_text="处理完成",
                progress_percent=100,
                processed_material_id=material_id,
                processed_filename=output_filename,
                processed_file_path=output_relative,
            )
        except Exception as exc:
            self._update_task(task_id, status="failed", progress_text="处理失败", error_message=str(exc))
        finally:
            self._release_slot()
            self._emit(callback, self.get_task(task_id))

    def _acquire_slot(self):
        with self.condition:
            while self.active_count >= self.get_settings().get("maxConcurrent", 4):
                self.condition.wait(timeout=2)
            self.active_count += 1

    def _release_slot(self):
        with self.condition:
            self.active_count = max(0, self.active_count - 1)
            self.condition.notify_all()

    def _update_task(self, task_id, **kwargs):
        with self.lock:
            self.tasks[task_id].update(kwargs)
            self.tasks[task_id]["updated_at"] = _now()

    def _emit(self, callback, payload):
        if callback:
            callback({"type": "processing", "data": payload})

    def _serialize_task(self, task: dict) -> dict:
        return {
            "taskId": task["task_id"],
            "status": task["status"],
            "progressText": task.get("progress_text"),
            "progressPercent": task.get("progress_percent"),
            "sourceMaterialId": task.get("source_material_id"),
            "processedMaterialId": task.get("processed_material_id"),
            "sourceFilename": task.get("source_filename"),
            "processedFilename": task.get("processed_filename"),
            "sourceFilePath": task.get("source_file_path"),
            "processedFilePath": task.get("processed_file_path"),
            "errorMessage": task.get("error_message"),
            "errorDetail": task.get("error_detail"),
            "config": task.get("config"),
            "createdAt": task.get("created_at"),
            "updatedAt": task.get("updated_at"),
        }


class DownloadService:
    def __init__(self, processing_service: ProcessingService | None = None):
        self.processing_service = processing_service or ProcessingService()
        self.tasks: dict[str, dict] = {}
        self.lock = threading.Lock()

    def create_youtube_download_task(
        self,
        url: str,
        download_subtitles: bool = True,
        callback: ProgressCallback | None = None,
    ) -> str:
        url = (url or "").strip()
        if not url:
            raise ServiceError("Video URL is required", "invalid_url")
        if not is_supported_youtube_url(url):
            raise ServiceError("Only single YouTube video URLs are supported", "invalid_url")
        if is_playlist_url(url):
            raise ServiceError("Playlist URLs are not supported", "invalid_url")

        task_id = uuid.uuid4().hex
        with self.lock:
            self.tasks[task_id] = self._new_task(task_id, url, bool(download_subtitles))
        threading.Thread(
            target=self._process_youtube_download,
            args=(task_id, url, bool(download_subtitles), callback),
            daemon=True,
        ).start()
        return task_id

    def list_youtube_tasks(self) -> list[dict]:
        with self.lock:
            tasks = [self._serialize_youtube_task(dict(task)) for task in self.tasks.values()]
        persisted = self._build_persisted_youtube_tasks()
        tasks.extend(persisted)
        return sorted(tasks, key=lambda item: (item.get("createdAt") or "", item.get("taskId") or ""), reverse=True)

    def get_youtube_task(self, task_id: str, include_subtitle_text: bool = True) -> dict:
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                raise ServiceError("Task not found", "not_found")
            return self._serialize_youtube_task(dict(task), include_subtitle_text=include_subtitle_text)

    def _process_youtube_download(self, task_id, url, download_subtitles, callback):
        try:
            self._update_task(task_id, status="downloading", phase="metadata", progress_text="正在读取视频信息")
            self._emit(callback, task_id)
            cookie_path = get_youtube_cookie_path()
            proxy = get_system_setting("download_proxy", "").strip() or None
            metadata = extract_video_metadata(
                url,
                proxy=proxy,
                cookiefile=str(cookie_path) if cookie_path else None,
            )
            title = metadata.get("title") or f"youtube_{task_id[:8]}"
            translated_title = translate_title_to_zh(title)
            safe_title = sanitize_filename(translated_title or title)
            self._update_task(
                task_id,
                video_id=metadata.get("id"),
                video_title=title,
                video_title_zh=translated_title,
                video_description=metadata.get("description"),
                video_resolution=metadata.get("resolution"),
            )
            self._emit(callback, task_id)

            def on_progress(status):
                progress_fields = self._extract_progress_fields(status)
                self._update_task(
                    task_id,
                    progress_text=self._format_download_progress(status),
                    phase="downloading",
                    **progress_fields,
                )
                self._emit(callback, task_id)

            final_path, subtitle_path = download_video(
                url,
                VIDEO_DIR,
                safe_title,
                download_subtitles=download_subtitles,
                progress_callback=on_progress,
                cookiefile=str(cookie_path) if cookie_path else None,
                proxy=proxy,
            )
            subtitle_relative = subtitle_path.name if subtitle_path else None
            if subtitle_path:
                translate_subtitle_file_to_zh(subtitle_path)
                embedded_path = embed_subtitle_into_video(final_path, subtitle_path)
                if embedded_path:
                    final_path = embedded_path
            resolution = detect_video_resolution(final_path.name) or metadata.get("resolution")
            material_id = create_material_record(
                filename=final_path.name,
                filepath=final_path.name,
                filesize_mb=round(final_path.stat().st_size / (1024 * 1024), 2),
                source_url=url,
                source_type="youtube",
                video_title=title,
                video_title_zh=translated_title,
                video_description=metadata.get("description"),
                subtitle_path=subtitle_relative,
                display_tags=["YouTube"],
                video_resolution=resolution,
            )
            self._update_task(
                task_id,
                status="success",
                progress_text="下载完成",
                progress_percent=100,
                phase="completed",
                material_id=material_id,
                filename=final_path.name,
                file_path=final_path.name,
                file_size_mb=round(final_path.stat().st_size / (1024 * 1024), 2),
                video_resolution=resolution,
                video_title=title,
                video_title_zh=translated_title,
                video_description=metadata.get("description"),
                subtitle_file_path=subtitle_relative,
            )
            if get_video_processing_settings().get("autoProcess", True):
                def on_processing_progress(event):
                    data = event.get("data", {}) if isinstance(event, dict) else {}
                    self._update_task(
                        task_id,
                        processing_status=data.get("status"),
                        processing_progress_text=data.get("progressText"),
                        processing_progress_percent=data.get("progressPercent"),
                        processed_material_id=data.get("processedMaterialId"),
                        processed_filename=data.get("processedFilename"),
                        processed_file_path=data.get("processedFilePath"),
                        processing_error_message=data.get("errorMessage"),
                        processing_error_detail=data.get("errorDetail"),
                    )
                    self._emit(callback, task_id)

                processing_task_id = self.processing_service.create_task(
                    material_id,
                    final_path.name,
                    final_path.name,
                    callback=on_processing_progress,
                )
                self._update_task(
                    task_id,
                    processing_task_id=processing_task_id,
                    processing_status="pending",
                    processing_progress_text="等待处理",
                    processing_progress_percent=0,
                )
        except Exception as exc:
            error_code, error_message, error_detail = classify_ytdlp_error(exc)
            self._update_task(
                task_id,
                status="failed",
                phase="failed",
                progress_text="下载失败",
                error_code=error_code,
                error_message=error_message,
                error_detail=error_detail,
            )
        finally:
            self._emit(callback, task_id)

    def _new_task(self, task_id, url, download_subtitles):
        return {
            "task_id": task_id,
            "status": "pending",
            "progress_text": "任务已创建",
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
            "video_resolution": None,
            "download_subtitles": download_subtitles,
            "subtitle_file_path": None,
            "subtitle_text": None,
            "filename": None,
            "file_path": None,
            "file_size_mb": None,
            "processing_task_id": None,
            "processing_status": None,
            "processing_progress_text": None,
            "processing_progress_percent": None,
            "processed_material_id": None,
            "processed_filename": None,
            "processed_file_path": None,
            "processing_error_message": None,
            "processing_error_detail": None,
            "created_at": _now(),
            "updated_at": _now(),
        }

    def _update_task(self, task_id, **kwargs):
        with self.lock:
            self.tasks[task_id].update(kwargs)
            self.tasks[task_id]["updated_at"] = _now()

    def _emit(self, callback, task_id):
        if callback:
            callback({"type": "download", "data": self.get_youtube_task(task_id, include_subtitle_text=False)})

    def _build_persisted_youtube_tasks(self):
        with db_connection() as conn:
            rows = conn.execute(
                """
                SELECT fr.*, pf.id AS proc_id, pf.filename AS proc_filename, pf.file_path AS proc_file_path
                FROM file_records fr
                LEFT JOIN file_records pf ON pf.parent_file_id = fr.id AND pf.material_type = 'processed'
                WHERE fr.source_type = 'youtube'
                ORDER BY fr.upload_time DESC, fr.id DESC
                """
            ).fetchall()
        return [self._serialize_youtube_task(self._build_persisted_youtube_task(row)) for row in rows]

    def _build_persisted_youtube_task(self, row):
        row_dict = dict(row)
        created_at = row_dict.get("upload_time")
        # Use cached resolution from DB instead of calling ffprobe every refresh
        resolution = row_dict.get("video_resolution") or ""
        # If not cached yet, probe and update (one-time migration)
        if not resolution and row_dict.get("file_path"):
            resolution = detect_video_resolution(row_dict.get("file_path"))
            if resolution:
                with db_connection() as conn:
                    conn.execute("UPDATE file_records SET video_resolution = ? WHERE id = ?", (resolution, row_dict["id"]))
        has_processed = row_dict.get("proc_id") is not None
        return {
            **self._new_task(f"material-{row_dict['id']}", row_dict.get("source_url"), bool(row_dict.get("subtitle_path"))),
            "status": "success",
            "progress_text": "下载完成",
            "progress_percent": 100,
            "phase": "completed",
            "material_id": row_dict["id"],
            "video_title": row_dict.get("video_title"),
            "video_title_zh": row_dict.get("video_title_zh"),
            "video_description": row_dict.get("video_description"),
            "video_resolution": resolution,
            "subtitle_file_path": row_dict.get("subtitle_path"),
            "filename": row_dict.get("filename"),
            "file_path": row_dict.get("file_path"),
            "file_size_mb": row_dict.get("filesize"),
            "processing_status": "success" if has_processed else None,
            "processing_progress_text": "处理完成" if has_processed else None,
            "processing_progress_percent": 100 if has_processed else None,
            "processed_material_id": row_dict.get("proc_id"),
            "processed_filename": row_dict.get("proc_filename"),
            "processed_file_path": row_dict.get("proc_file_path"),
            "created_at": created_at,
            "updated_at": created_at,
        }

    def _serialize_youtube_task(self, task, include_subtitle_text=False):
        subtitle_text = task.get("subtitle_text") or ""
        if include_subtitle_text and not subtitle_text:
            subtitle_text = read_subtitle_text(task.get("subtitle_file_path"))
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
            "resolution": task.get("video_resolution"),
            "downloadSubtitles": task.get("download_subtitles", True),
            "subtitleFilePath": task.get("subtitle_file_path"),
            "subtitleText": subtitle_text if include_subtitle_text else None,
            "filename": task.get("filename"),
            "filePath": task.get("file_path"),
            "fileSize": task.get("file_size_mb"),
            "processingTaskId": task.get("processing_task_id"),
            "processingStatus": task.get("processing_status"),
            "processingProgressText": task.get("processing_progress_text"),
            "processingProgressPercent": task.get("processing_progress_percent"),
            "processedMaterialId": task.get("processed_material_id"),
            "processedFilename": task.get("processed_filename"),
            "processedFilePath": task.get("processed_file_path"),
            "processingErrorMessage": task.get("processing_error_message"),
            "processingErrorDetail": task.get("processing_error_detail"),
            "createdAt": task.get("created_at"),
            "updatedAt": task.get("updated_at"),
        }

    def _format_download_progress(self, status):
        if status.get("status") == "downloading":
            parts = [
                (status.get("_percent_str") or "").strip(),
                (status.get("_speed_str") or "").strip(),
                f"ETA {(status.get('_eta_str') or '').strip()}" if status.get("_eta_str") else "",
            ]
            return " | ".join(part for part in parts if part) or "正在下载"
        if status.get("status") == "finished":
            return "下载完成，正在处理文件"
        return "等待下载"

    def _extract_progress_fields(self, status):
        percent_str = (status.get("_percent_str") or "").replace("%", "").strip()
        progress_percent = None
        if percent_str:
            try:
                progress_percent = round(float(percent_str), 2)
            except ValueError:
                progress_percent = None
        return {
            "progress_percent": progress_percent,
            "downloaded_bytes": status.get("downloaded_bytes"),
            "total_bytes": status.get("total_bytes") or status.get("total_bytes_estimate"),
            "speed_text": (status.get("_speed_str") or "").strip() or None,
            "eta_text": (status.get("_eta_str") or "").strip() or None,
        }

    def delete_youtube_task(self, task_id: str) -> dict:
        """Delete a download task and its associated files"""
        # First check if it's an in-memory task
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                # Remove from in-memory tasks
                del self.tasks[task_id]
                # If it has a material ID, delete the material
                if task.get("material_id"):
                    material_service = MaterialService()
                    return material_service.delete_material(task["material_id"])
                return {"taskId": task_id, "deleted": True}
        
        # Check if it's a persisted task (material record)
        if task_id.startswith("material-"):
            try:
                material_id = int(task_id.split("-", 1)[1])
                material_service = MaterialService()
                return material_service.delete_material(material_id)
            except (ValueError, ServiceError):
                raise ServiceError("Task not found", "not_found")
        
        raise ServiceError("Task not found", "not_found")

    def delete_youtube_tasks(self, task_ids: Iterable[str]) -> dict:
        """Delete multiple download tasks and their associated files"""
        deleted_items = []
        missing_ids = []
        
        for task_id in task_ids:
            try:
                deleted = self.delete_youtube_task(task_id)
                deleted_items.append({"taskId": task_id, **deleted})
            except ServiceError:
                missing_ids.append(task_id)
        
        return {"deleted": deleted_items, "missingIds": missing_ids}


class PublishService:
    def publish(self, payload: dict) -> None:
        file_list = payload.get("fileList", [])
        account_list = payload.get("accountList", [])
        platform_type = payload.get("type")
        title = payload.get("title")
        tags = payload.get("tags")
        category = payload.get("category")
        if category == 0:
            category = None
        if not file_list:
            raise ServiceError("fileList is required", "invalid_publish")
        if not account_list:
            raise ServiceError("accountList is required", "invalid_publish")
        if not platform_type:
            raise ServiceError("type is required", "invalid_publish")
        if not title:
            raise ServiceError("title is required", "invalid_publish")

        match platform_type:
            case 1:
                post_video_xhs(title, file_list, tags, account_list, category, payload.get("enableTimer"), payload.get("videosPerDay"), payload.get("dailyTimes"), payload.get("startDays"))
            case 2:
                post_video_tencent(title, file_list, tags, account_list, category, payload.get("enableTimer"), payload.get("videosPerDay"), payload.get("dailyTimes"), payload.get("startDays"), payload.get("isDraft", False))
            case 3:
                post_video_DouYin(title, file_list, tags, account_list, category, payload.get("enableTimer"), payload.get("videosPerDay"), payload.get("dailyTimes"), payload.get("startDays"), payload.get("thumbnail", ""), payload.get("productLink", ""), payload.get("productTitle", ""))
            case 4:
                post_video_ks(title, file_list, tags, account_list, category, payload.get("enableTimer"), payload.get("videosPerDay"), payload.get("dailyTimes"), payload.get("startDays"))
            case _:
                raise ServiceError(f"Unsupported platform type: {platform_type}", "unsupported_platform")

    def publish_batch(self, payloads: Iterable[dict]) -> None:
        for payload in payloads:
            self.publish(payload)


ensure_runtime_schema()