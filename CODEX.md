# 拾光分发 for Codex

## Project Overview

`拾光分发` 1.0 is a local Python desktop client for managing social-media upload workflows. The old Vue + Flask web path has been removed from the primary product surface.

## Tech Stack

- Desktop UI: `PySide6`
- Automation: `patchright` / Playwright-compatible browser automation
- Database: SQLite at `db/database.db`
- Runtime files: `videoFile/`, `cookiesFile/`, `cookies/`
- CLI: `sau ...`

## Running

```bash
pip install -r requirements.txt
playwright install chromium
python db/createTable.py
python -m sau_desktop.main
```

Editable install exposes the desktop entrypoint:

```bash
pip install -e .
sau-desktop
```

## Code Organization

- `sau_desktop/`: PySide6 local client.
- `sau_core/`: local service layer used by the desktop client and compatibility imports.
- `sau_cli.py`: command-line entrypoint.
- `myUtils/`, `uploader/`, `utils/`: platform automation and shared utilities.
- `sau_backend.py`: compatibility shim only; it no longer starts a Flask API.

## Working Notes

- Do not reintroduce HTTP as the desktop UI integration boundary.
- Prefer adding behavior to `sau_core` services, then call those services from PySide widgets.
- Keep UI dense and operational: tables, toolbars, split panes, compact forms.
- Preserve existing SQLite schema and runtime directory layout unless a migration is explicitly planned.
