from __future__ import annotations

import os
from pathlib import Path


def default_home() -> Path:
    override = os.environ.get("SAU_HOME")
    if override:
        return Path(override).expanduser().resolve()
    source_root = Path(__file__).resolve().parents[1]
    if (source_root / "pyproject.toml").is_file():
        from conf import BASE_DIR

        return Path(BASE_DIR).resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "Shiguang"
