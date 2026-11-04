# PAAI Render Queue

*PAAI = Prasenjeet Anand Artist Interface.*

Local render queue / dispatcher for **PAAI Pipeline** (Nuke, ComfyUI, Blender).

**Not tied to any show.** All queue data lives in a user data folder.

## Data location

Default:

```
<Documents>/PAAI Render Queue/
  settings.json
  jobs/
  scripts/
  logs/
```

Documents is resolved per OS (Windows Known Folder / OneDrive Documents when present, macOS `~/Documents`, Linux `XDG_DOCUMENTS_DIR` / `user-dirs.dirs`).

A small pointer file records the chosen folder so every submitter finds the same queue:

```
~/.paai/render_queue_location.json
```

Override with env `PAAI_RQ_HOME`, or pick another folder in **Settings** (optional “Move existing data”).

## Run

```bash
python3 -m paai_render_queue
# or choose a data folder / port:
python3 -m paai_render_queue --data "/path/to/PAAI Render Queue" --port 8790
./paai_render_queue/run_queue.sh
```

Open **http://127.0.0.1:8790/** (port configurable in Settings or `--port`).

## Settings

Web UI **Settings** (saved to `<data folder>/settings.json`):

- Data folder (+ move existing jobs/logs/scripts)
- Port
- Nuke & Blender launcher paths (Test buttons)
- ComfyUI server URLs (Test → `/system_stats`)
- Total CPU cores, max concurrent jobs, GPU list

Jobs may still store a show’s output path as metadata for “open in Render Browser”.

## Submit from DCCs

| App | Where |
|-----|--------|
| **Nuke** | **PAAI Pipeline → Submit to Render Queue** (`Ctrl+Shift+Q`) |
| **ComfyUI** | Top-bar **PAAI Pipeline → Submit to Queue** |
| **Blender** | Properties → Output → **PAAI Pipeline → Render Queue** |

If the queue server is not running, submitters write job JSON into the data folder and tell you to start the server. Put `paai_render_queue` on `PYTHONPATH` so submitters can import it.

## Execution

- **Nuke:** `nuke -x [-m cores] -X WriteName -F start-endxstep script.nk`
- **Blender:** `blender -b file.blend -S scene --python <override.py> -a`
- **ComfyUI:** `POST /prompt` to the chosen server; poll `/history`

## Coming soon

Coming soon: show-level EXR colorspace agreement.

PAAI = Prasenjeet Anand Artist Interface

Coming soon: show-level EXR colorspace agreement.

## Naming table

| Concept | Render Queue / job JSON | Notes |
|--------|-------------------------|-------|
| resources | `resources.cpu_cores`, `resources.gpu_index` | Old top-level `cpu_cores` still accepted |
| frames | `frames.start/end/step` | Default start 1001 from submitters |
| discovery | `~/.paai/render_queue_location.json` | Plus queue data home |
| show queue path | show_config `render_queue_path` | Install / discovery hint |


## Discovery (Windows / macOS / Linux)

On start the server writes:
- `<Documents>/PAAI Render Queue/queue_url.json` (Documents may be OneDrive-redirected on Windows)
- `~/.paai/render_queue_location.json` (includes `url`, `port`, `data_folder`)

DCC packs read those via bundled `paai_queue_link.py`. Start with `run_queue.bat` or `run_queue.sh`.
