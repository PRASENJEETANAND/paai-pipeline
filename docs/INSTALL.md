# Install

## Render Queue (do this first)

1. Unzip `paai_render_queue.zip`.
2. Start with `run_queue.bat` (Windows) or `run_queue.sh` / `python -m paai_render_queue`.
3. Open the URL printed in the console (default `http://127.0.0.1:8790`, or another port if busy).
4. Confirm Settings → data folder (defaults to Documents/`PAAI Render Queue`).

Discovery files written on start:
- `<Documents>/PAAI Render Queue/queue_url.json`
- `~/.paai/render_queue_location.json`

## Nuke 13–17

1. Download `nuke_paai_pipeline.zip` (flat archive).
2. Extract **all** files into `~/.nuke` (e.g. `C:\Users\<you>\.nuke\`).
3. Required: `menu.py`, `pipeline_*.py`, `render_*.py`, `scan.py`, `app_id.py`, `branding.py`, `paai_queue_link.py`, `paai_show.py`, `paai_show_ui.py`, `icons/`.
4. Restart Nuke. Menu **PAAI Pipeline** appears.

## Blender 4.2–5.1

1. Install `blender_paai_pipeline.zip` via *Edit → Preferences → Add-ons → Install*, **or** drop the folder into your versioned `scripts/addons/`.
2. Enable **PAAI Pipeline**. Top bar menu + Properties → Output panel.

`blender_manifest.toml` supports the 4.2+ extension system; `bl_info` remains for legacy install.

## ComfyUI

1. Unzip `comfyui_paai_pipeline.zip` into `ComfyUI/custom_nodes/`.
2. Install Python deps — see [DEPENDENCIES.md](DEPENDENCIES.md).
3. Restart ComfyUI. Top-bar **PAAI Pipeline** menu + nodes under category **PAAI Pipeline**.

## Show tree

```bash
python tools/paai_show.py create --root /path/to/SHOW --seq SQ010 --shots SH010,SH020
python tools/paai_show.py check --root /path/to/SHOW
```

Or use **Create / Check Show** inside each app.
