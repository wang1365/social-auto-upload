"""Install the Windows mpv/libmpv runtime used by desktop video preview."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "runtime" / "mpv"
RELEASES_API = "https://api.github.com/repos/zhongfly/mpv-winbuild/releases/latest"


def _download(url: str, target: Path) -> None:
    curl = shutil.which("curl")
    if curl:
        try:
            subprocess.run(
                [curl, "-L", "--retry", "5", "--retry-delay", "3", "--connect-timeout", "30", "-o", str(target), url],
                check=True,
            )
            if target.exists() and target.stat().st_size > 0:
                return
        except subprocess.CalledProcessError:
            if target.exists():
                target.unlink()
    request = urllib.request.Request(url, headers={"User-Agent": "social-auto-upload-runtime-installer"})
    last_error: Exception | None = None
    for _ in range(5):
        try:
            with urllib.request.urlopen(request, timeout=180) as response, target.open("wb") as output:
                shutil.copyfileobj(response, output)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(3)
    raise RuntimeError(f"Download failed after retries: {last_error}")


def _latest_libmpv_asset() -> tuple[str, str]:
    request = urllib.request.Request(RELEASES_API, headers={"User-Agent": "social-auto-upload-runtime-installer"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assets = payload.get("assets") or []
    for asset in assets:
        name = asset.get("name") or ""
        if name.startswith("mpv-dev-x86_64-") and name.endswith(".7z") and "-v3-" not in name:
            return name, asset["browser_download_url"]
    raise RuntimeError("No x86_64 libmpv asset found in latest zhongfly/mpv-winbuild release")


def _extract(archive: Path, target: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="sau-mpv-extract-") as temp_name:
        temp_dir = Path(temp_name)
        tar = shutil.which("tar")
        if tar:
            subprocess.run([tar, "-xf", str(archive), "-C", str(temp_dir)], check=True)
        else:
            shutil.unpack_archive(str(archive), str(temp_dir))
        dlls = list(temp_dir.rglob("*.dll"))
        if not any(path.name.lower() in {"libmpv-2.dll", "mpv-2.dll"} for path in dlls):
            raise RuntimeError("Downloaded archive did not contain libmpv-2.dll or mpv-2.dll")
        target.mkdir(parents=True, exist_ok=True)
        for source in dlls:
            shutil.copy2(source, target / source.name)
        for pattern in ("*.conf", "*.json", "*.txt", "*.md"):
            for source in temp_dir.rglob(pattern):
                if source.is_file() and source.parent == temp_dir:
                    shutil.copy2(source, target / source.name)


def _install_python_binding() -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "mpv==1.0.8"], check=True)


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("This installer currently targets Windows only")
    name, url = _latest_libmpv_asset()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    archive = RUNTIME_DIR / name
    print(f"Downloading {name}")
    _download(url, archive)
    print(f"Extracting to {RUNTIME_DIR}")
    _extract(archive, RUNTIME_DIR)
    print("Installing Python binding mpv==1.0.8")
    _install_python_binding()
    print("mpv runtime installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
