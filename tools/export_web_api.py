"""Export OpenAPI without starting workers or opening a user database."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sau_web.app import create_app  # noqa: E402

target = ROOT / "sau_frontend" / "openapi.json"
target.write_text(
    json.dumps(create_app(start_workers=False).openapi(), ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(target)
