from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

from sau_web.runtime import configure
from sau_web.store import Store


class Worker:
    def __init__(self, home, task_id):
        self.home = Path(home)
        self.services = configure(self.home)
        self.store = Store(self.services.DATABASE_PATH)
        self.task = self.store.get(task_id)
        self.id = task_id
        self.last_progress = 0.0

    def update(self, **kwargs):
        self.store.update(self.id, **kwargs)

    def record(self, message):
        # QR images, account cookies and download authentication must not enter logs.
        message = re.sub(r"data:image/[^\s]+", "[二维码]", str(message))
        message = re.sub(
            r"(?i)(cookie|authorization|token|password)[=:]\s*\S+",
            r"\1=[已隐藏]",
            message,
        )
        self.store.event(
            self.id,
            "log",
            {"message": self.services.strip_terminal_controls(message)[:3000]},
        )

    def account(self):
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_info WHERE id=?", (self.task["account_id"],)
            ).fetchone()
        if not row:
            raise ValueError("账号已删除")
        return dict(row)

    def material(self):
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM file_records WHERE id=?", (self.task["material_id"],)
            ).fetchone()
        if not row:
            raise ValueError("素材已删除")
        return dict(row)

    def progress(self, event):
        data = event.get("data", {})
        stamp = time.monotonic()
        if stamp - self.last_progress < 0.75 and data.get("status") not in {
            "success",
            "failed",
        }:
            return
        self.last_progress = stamp
        phase = data.get("progressText") or "执行中"
        if data.get("status") not in {"success", "failed"}:
            percent = (
                None
                if event.get("type") == "processing"
                else data.get("progressPercent")
            )
            self.update(phase=phase, progress=percent, result=data)

    def download(self):
        worker = self

        class ProcessingBridge:
            def create_task(self, material_id, source_path, filename, callback=None):
                payload = {
                    "material_id": material_id,
                    "config": worker.services.get_video_processing_settings(),
                }
                return worker.store.create(
                    "processing",
                    filename,
                    payload,
                    material_id=material_id,
                    parent_id=worker.id,
                )

        service = self.services.DownloadService(ProcessingBridge())
        payload = self.task["payload"]
        internal = service.create_youtube_download_task(
            payload["url"], payload["subtitles"], background=False
        )
        service._process_youtube_download(
            internal, payload["url"], payload["subtitles"], self.progress
        )
        result = service.get_youtube_task(internal)
        if result["status"] == "failed":
            self.update(
                status="failed",
                phase="下载失败",
                error=result.get("errorMessage"),
                detail=result.get("errorDetail"),
                result=result,
            )
        else:
            self.store.finish_download(self.id, result)

    def processing(self):
        material = self.material()
        service = self.services.ProcessingService()
        internal = service.create_task(
            material["id"],
            material["file_path"],
            material["filename"],
            background=False,
            config=self.task["payload"]["config"],
        )
        service._process_task(internal, self.progress)
        result = service.get_task(internal)
        self.update(
            status="succeeded" if result["status"] == "success" else "failed",
            phase=result["progressText"],
            progress=result.get("progressPercent"),
            error=result.get("errorMessage"),
            result=result,
        )

    async def account_task(self):
        from sau_web import adapters

        account = self.account()
        cookie = self.services.safe_relative_file(
            self.services.COOKIE_DIR, account["filePath"]
        )
        if self.task["kind"] == "check":
            self.update(phase="正在检查登录状态")
            valid = await adapters.check(account["type"], cookie)
            with self.store.connect() as conn:
                conn.execute(
                    "UPDATE user_info SET status=? WHERE id=?",
                    (int(valid), account["id"]),
                )
            self.update(
                status="succeeded",
                phase="登录有效" if valid else "登录已失效",
                result={"valid": valid},
            )
        else:
            self.update(phase="正在获取登录二维码")

            def qrcode(data):
                image = data.get("image_data_url", "")
                if not image.startswith("data:image/"):
                    return
                self.update(
                    phase="请使用对应平台 App 扫码登录", result={"qrcode": image}
                )

            await adapters.login(
                account["type"],
                cookie,
                qrcode,
                self.task["payload"].get("headed", False),
            )
            with self.store.connect() as conn:
                conn.execute(
                    "UPDATE user_info SET status=1 WHERE id=?", (account["id"],)
                )
            self.update(status="succeeded", phase="登录成功", result={"valid": True})

    async def publish(self):
        from sau_web import adapters

        account, material = self.account(), self.material()
        cookie = self.services.safe_relative_file(
            self.services.COOKIE_DIR, account["filePath"]
        )
        video = self.services.safe_relative_file(
            self.services.VIDEO_DIR, material["file_path"]
        )
        self.update(phase="检查账号与视频")
        if not await adapters.check(account["type"], cookie):
            with self.store.connect() as conn:
                conn.execute(
                    "UPDATE user_info SET status=0 WHERE id=?", (account["id"],)
                )
            raise ValueError("账号登录已失效，请重新登录")
        p = self.task["payload"]
        uploader = adapters.make_uploader(
            account["type"], cookie, video, p["title"], p["description"], p["tags"]
        )
        uploader.on_publish_attempt = lambda: self.update(
            phase="正在提交发布", result={"attempted": True}
        )
        uploader.on_upload_progress = lambda message: self.update(phase=message)
        uploader.on_publish_verification = lambda message: self.update(phase=message)
        uploader.publish_diagnostic_path = self.home / "runtime" / "publish-diagnostics" / self.id
        uploader.on_publish_confirmed = lambda: self.update(
            phase="平台已确认发布", result={"attempted": True, "confirmed": True}
        )
        self.update(phase="正在上传并填写文案")
        try:
            await asyncio.wait_for(uploader.main(), timeout=1800)
        except Exception as exc:
            if not getattr(uploader, "publish_confirmed", False):
                if getattr(uploader, "publish_attempted", False):
                    self.record(f"发布后未确认：{exc}")
                    self.update(
                        status="unknown",
                        phase="结果待核实，请先到平台确认",
                        error="抖音触发安全验证，尚未收到发布确认，请先到平台核实"
                        if getattr(uploader, "publish_verification_required", False)
                        else "提交后未能确认最终结果",
                    )
                    return
                raise
            self.record("平台已确认发布，后续清理失败，不重复提交")
        if not getattr(uploader, "publish_confirmed", False):
            self.update(
                status="unknown",
                phase="结果待核实，请先到平台确认",
                error="未收到平台发布确认",
            )
            return
        self.update(
            status="succeeded",
            phase="发布成功",
            progress=100,
            result={"confirmed": True},
        )

    def preview(self):
        material = self.material()
        source = self.services.safe_relative_file(
            self.services.VIDEO_DIR, material["file_path"]
        )
        target_dir = self.home / "runtime" / "previews"
        target_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("未找到 FFmpeg，请安装后重试")
        self.update(phase="正在准备预览")
        info = self.services.probe_video(source)
        (target_dir / f"{material['id']}.json").write_text(
            json.dumps(info), encoding="utf-8"
        )
        thumbnail = target_dir / f"{material['id']}.jpg"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                "scale=320:-2",
                str(thumbnail),
            ],
            capture_output=True,
            check=True,
            timeout=120,
        )
        if self.task["payload"].get("transcode"):
            target = target_dir / f"{material['id']}.mp4"
            temporary = target.with_suffix(".partial.mp4")
            try:
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-i",
                        str(source),
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "24",
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "aac",
                        "-movflags",
                        "+faststart",
                        str(temporary),
                    ],
                    capture_output=True,
                    check=True,
                    timeout=3600,
                )
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        self.update(
            status="succeeded",
            phase="预览已准备好",
            result={"materialId": material["id"]},
        )

    def run(self):
        from loguru import logger

        sink = logger.add(
            lambda message: self.record(message.record["message"]),
            level="INFO",
            catch=True,
        )
        self.record("开始执行任务")
        try:
            kind = self.task["kind"]
            if kind == "download":
                self.download()
            elif kind == "processing":
                self.processing()
            elif kind in {"login", "check"}:
                asyncio.run(self.account_task())
            elif kind == "publish":
                asyncio.run(self.publish())
            elif kind == "preview":
                self.preview()
            self.record(self.store.get(self.id)["phase"])
        except Exception as exc:
            # A receipt persisted before a later crash takes precedence.
            current = self.store.get(self.id)
            receipt = current["result"]
            status = "failed"
            if self.task["kind"] == "publish" and receipt.get("attempted"):
                status = "succeeded" if receipt.get("confirmed") else "unknown"
            self.update(
                status=status,
                phase="发布成功"
                if status == "succeeded"
                else (
                    "结果待核实，请先到平台确认" if status == "unknown" else "执行失败"
                ),
                error=str(exc)[:500],
                detail=traceback.format_exc()[-6000:],
                result={} if self.task["kind"] == "login" else receipt,
            )
            self.record(f"任务结束：{exc}")
        finally:
            logger.remove(sink)


if __name__ == "__main__":
    Worker(sys.argv[1], sys.argv[2]).run()
