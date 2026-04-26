## Project Overview

`拾光分发` 1.0 is a local desktop application for uploading and managing social-media publishing workflows. The product UI is implemented with PySide6 and calls Python services directly.

The previous Vue frontend and Flask HTTP API are legacy architecture and are not part of the 1.0 primary path.

## Core Components

**Desktop client**

- Package: `sau_desktop`
- Entry point: `python -m sau_desktop.main` or `sau-desktop`
- UI style: dense local-client layout with navigation, tables, toolbars, split panes, and compact forms.

**Service layer**

- Package: `sau_core`
- Services: accounts, materials, downloads, processing, publishing, settings.
- Data is stored in SQLite and local runtime folders.

**Automation and CLI**

- `uploader/`, `myUtils/`, and `utils/` contain platform-specific automation.
- `sau_cli.py` remains available for command-line workflows.

## Running

```bash
pip install -r requirements.txt
playwright install chromium
python db/createTable.py
python -m sau_desktop.main
```

For editable installs:

```bash
pip install -e .
sau-desktop
```

## Development Rules

- Do not add a Flask or REST dependency for desktop UI integration.
- Add business behavior to `sau_core` first, then connect UI widgets to service methods.
- Keep tests focused on services and automation boundaries; avoid UI tests that require real browser login.
- Keep the existing SQLite schema and runtime paths compatible by default.
