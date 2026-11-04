# PAAI Pipeline — Blender

PAAI = Prasenjeet Anand Artist Interface

Add-on **PAAI Pipeline**: Output panel, Render Browser (Qt/web), Render Queue submit.

Install: prefer `blender_paai_pipeline.zip` via Edit > Preferences > Add-ons > Install.

Coming soon: show-level EXR colorspace agreement.

## Naming table

| Concept | Blender property | show_config / files |
|--------|------------------|---------------------|
| version | `version` | folder `v###` |
| claim | `claim` (was `claim_version`) | `.claim` |
| allow overwrite | `allow_overwrite` | `allow_overwrite` (legacy `confirm_overwrite`) |
| start frame | scene frame_start + show | `start_frame` |
| queue path | `render_queue_path` | `render_queue_path` |
| type | `render_type` | `types.txt` / `default_type` |
| name | `name` | folder under type (`DEFAULT_NAME=main`) |
| sequence / shot | `sequence` / `shot` | prefs `sequence` (legacy `seq`) |

## Render Queue

Uses bundled `paai_queue_link.py` (stdlib HTTP) — the `paai_render_queue` package does **not** need to be on `sys.path`. Start the queue separately (`run_queue.bat`).

`blender_manifest.toml` supports Blender 4.2+ / 5.x extensions; `bl_info` remains for legacy Install Add-on.
