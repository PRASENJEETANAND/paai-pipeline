# Changelog

## v1.0.0 — 2026-11-04

First public suite release of **PAAI — Prasenjeet Anand Artist Interface**.

### Apps
- **Nuke** Write tab **PAAI Pipeline**, Render Browser (Qt), Render Queue submitter
- **Blender** 4.2–5.1 add-on: Output panel, Qt/web Render Browser, Render Queue panel
- **ComfyUI** custom nodes **PAAI Load** / **PAAI Write**, web Render Browser, queue submit
- **Render Queue** local dispatcher with web UI, port fallback, discovery files

### Pipeline
- Shared folder layout `<ROOT>/<SEQ>/<SHOT>/paai/<type>/[<name>/]v###/…`
- Atomic version **Claim**, overwrite guards, default start frame **1001**
- Unified `version_note.json`, shared format lists, path normalization
- App prefs: Nuke `~/.nuke/`; ComfyUI/Blender `~/.paai/<app>/`
- Show-level `render_queue_path`, `allow_overwrite`, `default_type`

### Tooling
- `paai_queue_link.py` — stdlib HTTP client (no queue package on DCC `sys.path`)
- `paai_show.py` — create / check show trees (CLI + in-app menus)
- `release/build_release.py` — builds the four install zips

### Branding
- π logo + tagline **Prasenjeet Anand Artist Interface** across UIs
