from __future__ import annotations

import asyncio
import hashlib
import io
import json
import mimetypes
import os
import secrets
import shutil
import subprocess
import threading
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from sau_web import schemas
from sau_web.adapters import PLATFORMS
from sau_web.paths import default_home
from sau_web.runtime import Runtime, configure
from sau_web.store import ACTIVE, Conflict, Store
from sau_web.youtube_browser import YouTubeBrowser, load_browser_cookies, youtube_video_url
from sau_web.youtube_cookies import browser_cookies_to_netscape

API = "/api/v2"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".flv", ".wmv"}


def create_app(home: Path | None = None, *, start_workers=True):
    if home is None:
        home = default_home()
    home = Path(home).resolve()
    store = Store(home / "db" / "database.db")
    runtime = Runtime(home, store)
    token = secrets.token_urlsafe(32)
    mutation_lock = threading.RLock()
    static = Path(__file__).parent / "static"
    youtube_browser = YouTubeBrowser(home)

    @asynccontextmanager
    async def lifespan(app):
        services = configure(home)
        store.migrate()
        services.ensure_runtime_schema()
        app.state.services = services
        if start_workers:
            runtime.start()
        try:
            yield
        finally:
            await youtube_browser.close()
            if start_workers:
                runtime.stop()

    app = FastAPI(
        title="拾光分发",
        version="2.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.store, app.state.runtime = store, runtime
    app.state.youtube_browser = youtube_browser
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )

    def error(message, code=400):
        raise HTTPException(code, message)

    @app.middleware("http")
    async def session_guard(request: Request, call_next):
        if request.url.path.startswith(API):
            fetch_site = request.headers.get("sec-fetch-site", "")
            origin = request.headers.get("origin")
            if fetch_site == "cross-site" or (
                origin and origin.rstrip("/") != str(request.base_url).rstrip("/")
            ):
                return JSONResponse({"message": "请求来源无效"}, status_code=403)
            public = request.url.path in {API + "/health", API + "/session"}
            if not public:
                cookie = request.cookies.get("sau_session", "")
                if not secrets.compare_digest(cookie, token):
                    return JSONResponse(
                        {"message": "本机会话已过期，请刷新页面"}, status_code=401
                    )
                if request.method not in {"GET", "HEAD", "OPTIONS"}:
                    if not secrets.compare_digest(
                        request.headers.get("x-sau-token", ""), token
                    ):
                        return JSONResponse(
                            {"message": "请求校验失败，请刷新页面"}, status_code=403
                        )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith(API):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse({"message": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        fields = [
            ".".join(str(item) for item in issue["loc"][1:]) for issue in exc.errors()
        ]
        labels = {
            "name": "账号名称",
            "platform": "所属平台",
            "items": "视频文案",
            "title": "视频标题",
            "description": "正文",
            "tags": "话题",
            "account_ids": "所选账号",
            "material_id": "所选素材",
            "url": "视频链接",
            "files": "视频文件",
            "file": "导入文件",
            "request_key": "提交信息",
            "page": "页码",
            "page_size": "每页数量",
        }
        hints = list(
            dict.fromkeys(
                labels.get(
                    str(issue["loc"][-1]), labels.get(str(issue["loc"][1]), "填写内容")
                )
                for issue in exc.errors()
            )
        )
        return JSONResponse(
            {
                "message": "请检查" + "、".join(hints) + "是否完整且符合要求",
                "fields": fields,
            },
            status_code=422,
        )

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"message": str(exc).strip("'")}, status_code=404)

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse({"message": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def bad_value(request, exc):
        return JSONResponse({"message": str(exc)}, status_code=400)

    def services():
        return app.state.services

    def account(account_id):
        with store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_info WHERE id=?", (account_id,)
            ).fetchone()
        if not row:
            error("账号不存在", 404)
        return dict(row)

    def material(material_id):
        with store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM file_records WHERE id=?", (material_id,)
            ).fetchone()
        if not row:
            error("素材不存在", 404)
        return dict(row)

    def material_path(material_id):
        row = material(material_id)
        path = services().safe_relative_file(services().VIDEO_DIR, row["file_path"])
        if not path.is_file():
            error("素材文件不存在", 404)
        return row, path

    def enrich(row):
        data = services().build_material_row(row)
        cached = home / "runtime" / "previews" / f"{row['id']}.json"
        try:
            data["duration"] = json.loads(cached.read_text(encoding="utf-8")).get(
                "duration"
            )
        except (OSError, ValueError):
            data["duration"] = None
        data["has_thumbnail"] = cached.with_suffix(".jpg").is_file()
        data["has_subtitle"] = bool(row.get("subtitle_path"))
        return data

    def resource_guard(conn, resource, resource_id):
        column = "account_id" if resource == "account" else "material_id"
        query = f"SELECT 1 FROM web_tasks WHERE status IN ('queued','running') AND {column}=?"
        if resource == "material":
            query = "SELECT 1 FROM web_tasks WHERE status IN ('queued','running') AND (material_id=? OR json_extract(result,'$.materialId')=?)"
            args = (resource_id, resource_id)
        else:
            args = (resource_id,)
            query = """SELECT 1 FROM web_tasks WHERE status IN ('queued','running') AND
                (account_id=? OR (kind='download' AND EXISTS
                (SELECT 1 FROM json_each(payload,'$.publish_jobs') j
                WHERE json_extract(j.value,'$.account_id')=?)))"""
            args = (resource_id, resource_id)
        if conn.execute(query, args).fetchone():
            raise Conflict(
                "该账号有任务正在执行或排队"
                if resource == "account"
                else "该素材正在被任务使用，请等待任务结束"
            )

    def queue(kind, title, payload, **refs):
        return {"id": store.create(kind, title, payload, **refs)}

    @app.get(API + "/health")
    def health():
        return {"application": "social-auto-upload", "version": "2.0.0", "ready": True}

    @app.get(API + "/session")
    def session():
        response = JSONResponse({"token": token})
        response.set_cookie("sau_session", token, httponly=True, samesite="strict")
        return response

    @app.get(API + "/openapi.json")
    def openapi():
        return app.openapi()

    @app.get(API + "/platforms")
    def platforms():
        return [{"id": key, **value} for key, value in PLATFORMS.items()]

    @app.get(API + "/accounts", response_model=list[schemas.Account])
    def accounts():
        return services().AccountService().list_accounts()

    @app.post(API + "/accounts", response_model=schemas.Account, status_code=201)
    def create_account(body: schemas.AccountInput):
        with mutation_lock, store.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO user_info(type,filePath,userName,status) VALUES(?,?,?,0)",
                (body.platform, f"{uuid.uuid4().hex}.json", body.name),
            )
            account_id = cursor.lastrowid
        store.event(None, "accounts", {})
        return {**account(account_id), "platform": PLATFORMS[body.platform]["name"]}

    @app.patch(API + "/accounts/{account_id}", response_model=schemas.Account)
    def rename_account(account_id: int, body: schemas.AccountInput):
        row = account(account_id)
        if body.platform != row["type"]:
            error("账号平台不能修改，请添加新账号")
        with mutation_lock, store.connect() as conn:
            conn.execute(
                "UPDATE user_info SET userName=? WHERE id=?", (body.name, account_id)
            )
        store.event(None, "accounts", {})
        return {**account(account_id), "platform": PLATFORMS[row["type"]]["name"]}

    @app.delete(API + "/accounts/{account_id}", status_code=204)
    def delete_account(account_id: int):
        row = account(account_id)
        with mutation_lock, store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            resource_guard(conn, "account", account_id)
            path = services().safe_relative_file(services().COOKIE_DIR, row["filePath"])
            path.unlink(missing_ok=True)
            conn.execute("DELETE FROM user_info WHERE id=?", (account_id,))
        store.event(None, "accounts", {})
        return Response(status_code=204)

    @app.post(
        API + "/accounts/{account_id}/login",
        response_model=schemas.TaskCreated,
        status_code=202,
    )
    def login(account_id: int, body: schemas.LoginInput):
        row = account(account_id)
        with mutation_lock:
            if store.busy("account", account_id):
                raise Conflict("账号已有任务，请等待任务结束")
            return queue(
                "login",
                f"登录 · {row['userName']}",
                body.model_dump(),
                account_id=account_id,
            )

    @app.post(
        API + "/accounts/{account_id}/check",
        response_model=schemas.TaskCreated,
        status_code=202,
    )
    def check_account(account_id: int):
        row = account(account_id)
        with mutation_lock:
            if store.busy("account", account_id):
                raise Conflict("账号已有任务，请等待任务结束")
            return queue(
                "check", f"检查 · {row['userName']}", {}, account_id=account_id
            )

    @app.get(API + "/accounts/{account_id}/cookie")
    def export_cookie(account_id: int):
        row = account(account_id)
        path = services().safe_relative_file(services().COOKIE_DIR, row["filePath"])
        if not path.is_file():
            error("该账号尚未登录", 404)
        return FileResponse(
            path, filename=f"account-{account_id}.json", media_type="application/json"
        )

    @app.post(
        API + "/accounts/{account_id}/cookie",
        response_model=schemas.TaskCreated,
        status_code=202,
    )
    def import_cookie(account_id: int, file: UploadFile = File(...)):
        row = account(account_id)
        with mutation_lock:
            if store.busy("account", account_id):
                raise Conflict("账号有任务正在执行或排队")
            raw = file.file.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                error("Cookie 文件过大")
            try:
                data = json.loads(raw)
                if (
                    not isinstance(data, dict)
                    or not isinstance(data.get("cookies"), list)
                    or not isinstance(data.get("origins", []), list)
                ):
                    raise ValueError()
            except (ValueError, UnicodeError):
                error("请选择有效的浏览器登录状态 JSON 文件")
            target = services().safe_relative_file(
                services().COOKIE_DIR, row["filePath"]
            )
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(raw)
            temporary.replace(target)
            with store.connect() as conn:
                conn.execute("UPDATE user_info SET status=0 WHERE id=?", (account_id,))
            return queue(
                "check", f"检查 · {row['userName']}", {}, account_id=account_id
            )

    @app.get(API + "/materials", response_model=schemas.MaterialPage)
    def materials(
        q: str = "",
        source: str = "",
        page: int = Query(1, ge=1),
        page_size: int = Query(30, ge=1, le=100),
    ):
        rows = services().MaterialService().list_materials()
        if q:
            rows = [
                row
                for row in rows
                if q.casefold()
                in " ".join(
                    str(row.get(key) or "")
                    for key in ("filename", "video_title", "video_title_zh")
                ).casefold()
            ]
        if source:
            rows = [
                row
                for row in rows
                if (row.get("source_type") or row.get("material_type")) == source
            ]
        return {
            "items": [
                enrich(row) for row in rows[(page - 1) * page_size : page * page_size]
            ],
            "total": len(rows),
            "page": page,
            "page_size": page_size,
        }

    @app.get(API + "/materials/{material_id}", response_model=schemas.Material)
    def get_material(material_id: int):
        return enrich(material(material_id))

    @app.post(
        API + "/materials", response_model=list[schemas.Material], status_code=201
    )
    def upload_materials(files: list[UploadFile] = File(...)):
        if not files or len(files) > 100:
            error("每次请选择 1 至 100 个视频")
        for file in files:
            filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
            if Path(filename).suffix.lower() not in VIDEO_EXTENSIONS:
                error(f"不支持的视频格式：{filename}")
        imported = []
        try:
            for file in files:
                filename = file.filename.replace("\\", "/").rsplit("/", 1)[-1]
                filename = re_safe_filename(filename)
                stored_name = f"{uuid.uuid4().hex}_{filename}"
                target = services().VIDEO_DIR / stored_name
                temporary = target.with_suffix(target.suffix + ".partial")
                try:
                    with temporary.open("wb") as output:
                        shutil.copyfileobj(file.file, output, length=1024 * 1024)
                    if not temporary.stat().st_size:
                        error("不能导入空文件")
                    temporary.replace(target)
                    material_id = services().create_material_record(
                        filename, stored_name, round(target.stat().st_size / 1024**2, 2)
                    )
                    imported.append(material_id)
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
                finally:
                    temporary.unlink(missing_ok=True)
            for material_id in imported:
                if shutil.which("ffmpeg"):
                    queue(
                        "preview",
                        f"读取视频信息 · {material(material_id)['filename']}",
                        {"transcode": False},
                        material_id=material_id,
                    )
        except Exception:
            for material_id in imported:
                services().MaterialService().delete_material(material_id)
            raise
        store.event(None, "materials", {})
        return [enrich(material(material_id)) for material_id in imported]

    @app.delete(API + "/materials/{material_id}", status_code=204)
    def delete_material(material_id: int):
        material(material_id)
        with mutation_lock, store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            resource_guard(conn, "material", material_id)
            services().delete_material_record(conn, material_id)
        for suffix in (".mp4", ".jpg", ".json", ".partial.mp4"):
            (home / "runtime" / "previews" / f"{material_id}{suffix}").unlink(
                missing_ok=True
            )
        store.event(None, "materials", {})
        return Response(status_code=204)

    @app.get(API + "/materials/{material_id}/video")
    def video(material_id: int, compatible: bool = False):
        row, path = material_path(material_id)
        if compatible:
            path = home / "runtime" / "previews" / f"{material_id}.mp4"
            if not path.is_file():
                error("兼容预览尚未生成", 404)
        return FileResponse(
            path, media_type=mimetypes.guess_type(path.name)[0] or "video/mp4"
        )

    @app.get(API + "/materials/{material_id}/thumbnail")
    def thumbnail(material_id: int):
        material(material_id)
        path = home / "runtime" / "previews" / f"{material_id}.jpg"
        if not path.is_file():
            error("暂无缩略图", 404)
        return FileResponse(path, media_type="image/jpeg")

    @app.get(API + "/materials/{material_id}/subtitle")
    def subtitle(material_id: int):
        row = material(material_id)
        return {"text": services().read_subtitle_text(row.get("subtitle_path"))}

    @app.post(
        API + "/materials/{material_id}/preview",
        response_model=schemas.TaskCreated,
        status_code=202,
    )
    def preview(material_id: int):
        with mutation_lock:
            row, path = material_path(material_id)
            for task in store.list(kind="preview", limit=10000):
                if (
                    task["material_id"] == material_id
                    and task["status"] in ACTIVE
                    and task["payload"].get("transcode")
                ):
                    return {"id": task["id"]}
            return queue(
                "preview",
                f"生成兼容预览 · {row['filename']}",
                {"transcode": True},
                material_id=material_id,
            )

    @app.post(API + "/materials/{material_id}/reveal", status_code=204)
    def reveal(material_id: int):
        row, path = material_path(material_id)
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", "/select,", str(path)])
        elif sys_platform() == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
        return Response(status_code=204)

    @app.post(
        API + "/publish-batches", response_model=schemas.BatchResult, status_code=202
    )
    def publish(body: schemas.PublishBatch):
        with mutation_lock:
            chosen_accounts = [
                account(item) for item in dict.fromkeys(body.account_ids)
            ]
            if any(row["status"] != 1 for row in chosen_accounts):
                error("所选账号包含未登录或失效账号，请先登录")
            if len({item.material_id for item in body.items}) != len(body.items):
                error("同一批次不能重复选择素材")
            jobs = []
            for item in body.items:
                row, path = material_path(item.material_id)
                for selected in chosen_accounts:
                    jobs.append(
                        {
                            **item.model_dump(),
                            "account_id": selected["id"],
                            "account_name": selected["userName"],
                            "platform": selected["type"],
                            "filename": row["filename"],
                            "description": item.description
                            if PLATFORMS[selected["type"]]["description"]
                            else "",
                        }
                    )
            fingerprint = hashlib.sha256(
                json.dumps(
                    body.model_dump(exclude={"request_key"}),
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
            batch_id = store.create_batch(body.request_key, fingerprint, jobs)
        return store.batch(batch_id)

    @app.get(API + "/publish-batches/{batch_id}", response_model=schemas.BatchResult)
    def get_batch(batch_id: str):
        return store.batch(batch_id)

    @app.post(API + "/downloads", response_model=schemas.TaskCreated, status_code=202)
    def download(body: schemas.DownloadInput):
        if not services().is_supported_youtube_url(
            body.url
        ) or services().is_playlist_url(body.url):
            error("请输入单个 YouTube 视频链接，暂不支持播放列表")
        return queue("download", body.url, body.model_dump())

    @app.get(API + "/youtube/browser", response_model=schemas.BrowserState)
    async def youtube_state(snapshot: bool = False):
        return await youtube_browser.state(snapshot)

    @app.post(API + "/youtube/browser/media")
    async def youtube_media(body: schemas.MediaOffer):
        return await youtube_browser.media_offer(body.model_dump())

    @app.delete(API + "/youtube/browser/media/{peer_id}", status_code=204)
    async def youtube_media_close(peer_id: str):
        await youtube_browser.close_media(peer_id)
        return Response(status_code=204)

    @app.post(API + "/youtube/browser/start", response_model=schemas.BrowserState)
    async def youtube_start():
        cookie_file = services().get_youtube_cookie_path()
        return await youtube_browser.start(
            services().get_system_setting("download_proxy", "").strip(),
            cookies=load_browser_cookies(cookie_file) if cookie_file else None,
        )

    @app.post(API + "/youtube/browser/action", response_model=schemas.BrowserState)
    async def youtube_action(body: schemas.BrowserAction):
        return await youtube_browser.action(body)

    @app.delete(API + "/youtube/browser", status_code=204)
    async def youtube_close():
        await youtube_browser.close()
        return Response(status_code=204)

    @app.post(API + "/youtube/downloads", response_model=schemas.TaskCreated, status_code=202)
    def youtube_download(body: schemas.YouTubeDownloadInput):
        url = youtube_video_url(body.url)
        if not url:
            error("请先在 YouTube 打开一条视频，再下载或发布")
        if body.account_ids and not body.title.strip():
            error("请填写发布标题")
        with mutation_lock:
            jobs = []
            for account_id in dict.fromkeys(body.account_ids):
                selected = account(account_id)
                if selected["status"] != 1:
                    error("所选账号包含未登录或失效账号，请先登录")
                item = schemas.PublishItem(material_id=1, title=body.title,
                    description=body.description, tags=body.tags) if body.account_ids else None
                jobs.append({"account_id": account_id, "account_name": selected["userName"],
                    "platform": selected["type"], "title": item.title, "tags": item.tags,
                    "description": item.description if PLATFORMS[selected["type"]]["description"] else ""})
            payload = {"url": url, "subtitles": body.subtitles, "publish_jobs": jobs}
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            return {"id": store.create_youtube_download(body.request_key, fingerprint, payload)}

    @app.post(API + "/processing", response_model=schemas.TaskCreated, status_code=202)
    def process(body: schemas.ProcessingInput):
        with mutation_lock:
            row, path = material_path(body.material_id)
            return queue(
                "processing",
                row["filename"],
                {
                    "material_id": row["id"],
                    "config": services().get_video_processing_settings(),
                },
                material_id=row["id"],
            )

    @app.get(API + "/tasks", response_model=list[schemas.Task])
    def tasks(
        kind: schemas.Kind | None = None,
        parent_id: str | None = None,
        limit: int = Query(200, ge=1, le=10000),
    ):
        return store.list(kind, parent_id, limit)

    @app.get(API + "/tasks/{task_id}", response_model=schemas.Task)
    def get_task(task_id: str):
        return store.get(task_id)

    @app.get(API + "/tasks/{task_id}/logs", response_model=list[schemas.TaskEvent])
    def logs(task_id: str, after: int = Query(0, ge=0)):
        store.get(task_id)
        return store.events(after, task_id, 500)

    @app.post(
        API + "/tasks/{task_id}/retry",
        response_model=schemas.TaskCreated,
        status_code=202,
    )
    def retry(task_id: str):
        with mutation_lock:
            task = store.get(task_id)
            if task["status"] not in {"failed", "interrupted"}:
                raise Conflict(
                    "只能重试明确失败或中断的任务；发布结果待核实的任务请先到平台确认"
                )
            if task["result"].get("retry_status") in {"succeeded", "unknown"}:
                raise Conflict("此任务的后续重试已完成或结果待核实，不能重复提交")
            if task["account_id"]:
                account(task["account_id"])
            if task["material_id"]:
                material_path(task["material_id"])
            if task["kind"] == "publish" and task["result"].get("attempted"):
                raise Conflict("该任务已尝试提交，请先核实发布结果")
            # One retry chain per original task prevents double-click retries.
            for child in store.retry_chain(task_id):
                if child["kind"] != task["kind"]:
                    continue
                if child["status"] in {"succeeded", "unknown"}:
                    raise Conflict("此任务的重试已完成或结果待核实，请查看最新记录")
                if child["status"] in ACTIVE:
                    return {"id": child["id"]}
            if task["account_id"] and store.busy("account", task["account_id"]):
                raise Conflict("账号已有任务，请等待执行结束")
            return queue(
                task["kind"],
                task["title"],
                task["payload"],
                account_id=task["account_id"],
                material_id=task["material_id"],
                parent_id=task_id,
            )

    @app.post(API + "/tasks/{task_id}/cancel", status_code=204)
    def cancel(task_id: str):
        store.cancel(task_id)
        return Response(status_code=204)

    @app.delete(API + "/tasks/{task_id}", status_code=204)
    def delete_task(task_id: str):
        store.delete(task_id)
        return Response(status_code=204)

    @app.get(API + "/settings")
    def settings():
        from myUtils.video_processor import DEFAULT_VIDEO_PROCESSING_CONFIG

        return {
            **services().SettingsService().get_settings(),
            "defaultVideoProcessing": DEFAULT_VIDEO_PROCESSING_CONFIG,
            "tools": {
                "ffmpeg": bool(shutil.which("ffmpeg")),
                "ffprobe": bool(shutil.which("ffprobe")),
            },
        }

    @app.put(API + "/settings")
    def save_settings(body: schemas.SettingsInput):
        return (
            services()
            .SettingsService()
            .save_settings(
                body.downloadProxy, body.videoProcessing, body.publishTopicPresets,
                body.llm.model_dump() if body.llm else None,
                body.translation.model_dump() if body.translation else None,
            )
        )

    @app.post(API + "/settings/translation/test")
    def test_translation():
        from sau_core.title_translation import translate_title_to_zh
        return {"title": translate_title_to_zh("A beautiful day in Tokyo", strict=True)}

    def save_youtube_cookie(data):
        if len(data) > 2 * 1024 * 1024:
            error("Cookie 文件过大")
        temporary = services().SYSTEM_COOKIE_DIR / f"{uuid.uuid4().hex}.txt"
        try:
            temporary.write_bytes(data)
            return services().SettingsService().upload_youtube_cookie(temporary)
        finally:
            temporary.unlink(missing_ok=True)

    @app.post(API + "/settings/youtube-cookie")
    def youtube_cookie(file: UploadFile = File(...)):
        data = file.file.read(2 * 1024 * 1024 + 1)
        services().validate_netscape_cookie_text(file.filename or "cookies.txt", data)
        with mutation_lock:
            return save_youtube_cookie(data)

    @app.post(API + "/settings/youtube-cookie/browser")
    def import_browser_cookie(body: schemas.BrowserCookieImport):
        data = browser_cookies_to_netscape(body.cookies)
        with mutation_lock:
            return save_youtube_cookie(data)

    @app.get(API + "/settings/browser-helper.zip")
    def browser_helper():
        source = Path(__file__).parent / "browser_helper"
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name in ("manifest.json", "background.js", "content.js", "README.txt"):
                bundle.write(source / name, name)
        return Response(archive.getvalue(), media_type="application/zip", headers={
            "Content-Disposition": 'attachment; filename="shiguang-browser-helper.zip"',
        })

    @app.delete(API + "/settings/youtube-cookie", status_code=204)
    def clear_youtube_cookie():
        with mutation_lock:
            services().SettingsService().clear_youtube_cookie()
        return Response(status_code=204)

    @app.get(API + "/events")
    async def events(request: Request, after: int = Query(0, ge=0)):
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            error("事件游标无效")
        if cursor > store.latest_event():
            cursor = 0

        async def stream():
            nonlocal cursor
            # Establish the stream immediately; callers fetch fresh snapshots too.
            yield ": connected\n\n"
            idle = 0
            while not await request.is_disconnected():
                rows = await asyncio.to_thread(store.events, cursor)
                for row in rows:
                    cursor = row["id"]
                    yield f"id: {cursor}\ndata: {json.dumps(row, ensure_ascii=False)}\n\n"
                idle += 1
                if idle % 15 == 0:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )

    # Exception import here avoids exposing third-party internals in error responses.
    from sau_core.services import ServiceError

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        messages = {
            "invalid_proxy": "请输入有效的 HTTP、HTTPS 或 SOCKS5 代理地址",
            "invalid_cookie": "登录凭据文件格式无效，请检查后重新导入",
            "missing_cookie": "已保存的 YouTube Cookie 文件不存在，请在设置中重新导入",
            "invalid_path": "文件路径无效",
            "missing_file": "找不到所选文件",
        }
        return JSONResponse(
            {"message": messages.get(exc.code, str(exc)), "code": exc.code},
            status_code=400,
        )

    if static.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=static / "assets", check_dir=False),
            name="assets",
        )

    @app.get("/{path:path}", include_in_schema=False)
    def index(path: str):
        if path.startswith("api/"):
            error("接口不存在", 404)
        if (static / "index.html").is_file():
            return FileResponse(
                static / "index.html", headers={"Cache-Control": "no-cache"}
            )
        return JSONResponse(
            {"message": "前端资源未构建，请先按开发文档构建前端"}, status_code=503
        )

    return app


def re_safe_filename(value):
    import re

    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)[:180] or "video.mp4"


def sys_platform():
    import sys

    return sys.platform
