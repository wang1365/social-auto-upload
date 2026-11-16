from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from sau_web.store import Store


def configure(home: Path):
    # Services read these paths at call time. Worker processes receive the same home.
    import sau_core.services as services

    home = Path(home).resolve()
    services.DATABASE_PATH = home / "db" / "database.db"
    services.VIDEO_DIR = home / "videoFile"
    services.COOKIE_DIR = home / "cookiesFile"
    services.SYSTEM_COOKIE_DIR = services.COOKIE_DIR / "system"
    return services


class Runtime:
    """One supervisor; task workers are isolated Python processes, never HTTP workers."""

    def __init__(self, home: Path, store: Store):
        self.home, self.store = Path(home), store
        self.stopping = threading.Event()
        self.processes: dict[str, tuple[subprocess.Popen, dict, float]] = {}
        self.thread = None
        self.lock_file = None

    def start(self):
        lock_path = self.home / "runtime" / "web.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file = lock_path.open("a+b")
        self.lock_file.write(b"0")
        self.lock_file.flush()
        self.lock_file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock_file.close()
            raise RuntimeError("拾光分发服务已运行，请打开已有窗口")
        self.store.recover()
        self.thread = threading.Thread(
            target=self.loop, name="sau-supervisor", daemon=True
        )
        self.thread.start()

    def loop(self):
        while not self.stopping.wait(0.5):
            try:
                self.tick()
            except Exception:
                import logging

                logging.getLogger(__name__).exception("任务调度失败")

    def tick(self):
        for task_id, (process, task, started) in list(self.processes.items()):
            timed_out = time.monotonic() - started > (
                2100 if task["kind"] == "publish" else 7200
            )
            if process.poll() is None and not timed_out:
                continue
            if timed_out:
                self._stop_process(process)
            state = self.store.get(task_id)
            if state["status"] == "running":
                status = "unknown" if task["kind"] == "publish" else "interrupted"
                if task["kind"] == "publish" and state["result"].get("confirmed"):
                    status = "succeeded"
                self.store.update(
                    task_id,
                    status=status,
                    phase="发布成功"
                    if status == "succeeded"
                    else (
                        "结果待核实，请先到平台确认"
                        if status == "unknown"
                        else "任务执行中断"
                    ),
                    error=None if status == "succeeded" else "执行进程退出或超时",
                )
            del self.processes[task_id]
        from sau_core.services import get_video_processing_settings

        limits = {
            "publish": 1,
            "download": 2,
            "processing": get_video_processing_settings().get("maxConcurrent", 4),
            "login": 2,
            "check": 2,
            "preview": 1,
        }
        running = [task for _, task, _ in self.processes.values()]
        accounts = {task["account_id"] for task in running if task["account_id"]}
        counts = {
            kind: sum(task["kind"] == kind for task in running) for kind in limits
        }
        for task in reversed(self.store.list(limit=10000)):
            kind = task["kind"]
            if task["status"] != "queued" or counts[kind] >= limits[kind]:
                continue
            if task["account_id"] and task["account_id"] in accounts:
                continue
            if not self.store.claim(task["id"]):
                continue
            try:
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                command = (
                    [sys.executable, "--worker", str(self.home), task["id"]]
                    if getattr(sys, "frozen", False)
                    else [
                        sys.executable,
                        "-m",
                        "sau_web.worker",
                        str(self.home),
                        task["id"],
                    ]
                )
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                    start_new_session=os.name != "nt",
                )
            except Exception as exc:
                self.store.update(
                    task["id"], status="failed", phase="无法启动任务", error=str(exc)
                )
                continue
            self.processes[task["id"]] = (process, task, time.monotonic())
            counts[kind] += 1
            if task["account_id"]:
                accounts.add(task["account_id"])

    @staticmethod
    def _stop_process(process):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            import signal

            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=5)
        for process, _, _ in self.processes.values():
            self._stop_process(process)
        self.store.recover()
        if self.lock_file:
            self.lock_file.close()
