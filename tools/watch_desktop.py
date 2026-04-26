from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


WATCH_DIRS = ["sau_desktop", "sau_core", "myUtils"]
WATCH_SUFFIXES = {".py", ".json", ".toml"}


def snapshot(root: Path) -> dict[Path, int]:
    state = {}
    for dirname in WATCH_DIRS:
        directory = root / dirname
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix in WATCH_SUFFIXES:
                try:
                    state[path] = path.stat().st_mtime_ns
                except OSError:
                    continue
    return state


def start_app(root: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.Popen(
        [sys.executable, "-m", "sau_desktop.main"],
        cwd=root,
        env=env,
    )


def stop_app(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    previous = snapshot(root)
    process = start_app(root)
    print("Watching sau_desktop, sau_core, myUtils. Change files to restart the desktop app.", flush=True)
    try:
        while True:
            time.sleep(0.6)
            current = snapshot(root)
            if current != previous:
                previous = current
                print("Change detected. Restarting desktop app...", flush=True)
                stop_app(process)
                process = start_app(root)
            elif process.poll() is not None:
                print(f"Desktop app exited with code {process.returncode}. Waiting for changes.", flush=True)
                process = start_app(root)
    except KeyboardInterrupt:
        stop_app(process)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
