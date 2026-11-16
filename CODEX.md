# 拾光分发 2.0

## Architecture

- Product UI: Vue 3 + TypeScript + Element Plus in `sau_frontend/`.
- Local HTTP API: FastAPI in `sau_web/`, `/api/v2`, loopback only.
- Runtime: SQLite-backed task supervisor and isolated Python worker processes.
- Business services: `sau_core/`; platform automation: `uploader/`.
- CLI: `sau ...`; web: `sau-web` or `python -m sau_web.launcher`.
- PySide6 desktop UI has been removed. Do not reintroduce Qt or mpv.

## Working rules

- Keep UI Chinese, concise, and oriented around material/account/publishing workflows.
- Put validation, orchestration, and publishing receipts in Python, not page widgets.
- Preserve SQLite schema, IDs, cookies and material paths; back up before migrations.
- Never infer publishing success solely from an absence of exceptions. Submission without a positive receipt is unknown and must not auto-retry.
- Guard active material/account references. Deleting task history must retain material files.
- Session cookies protect media and SSE; mutations also require the local CSRF token.
- Generate frontend API types with `python tools/export_web_api.py` and `npm --prefix sau_frontend run api:types`.
- Read `docs/web-2.0.md` for build, tests, migration, and recovery.
- Tests use isolated runtime directories and mocked platforms; do not publish real content during automated checks.

## Verification

```powershell
uv run pytest -q
npm.cmd --prefix sau_frontend test
npm.cmd --prefix sau_frontend run build
```
