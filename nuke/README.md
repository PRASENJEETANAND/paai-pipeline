# PAAI Pipeline — Nuke

PAAI = Prasenjeet Anand Artist Interface

Adds a **PAAI Pipeline** tab on Nuke Write nodes, a Render Browser, and Render Queue submit.

## Install (flat into ~/.nuke — recommended on Windows)

The zip is **flat** (files at the archive root). Extract / copy **every file** into your Nuke profile, e.g. `C:\Users\<you>\.nuke\`:

| Required files / folders |
|--------------------------|
| `menu.py` |
| `pipeline_write.py` |
| `pipeline_config.py` |
| `render_browser.py` |
| `render_queue_submit.py` |
| `scan.py` |
| `app_id.py` |
| `branding.py` |
| `paai_queue_link.py` |
| `icons/` (logo PNGs) |

Do **not** copy only `menu.py` — helpers like `scan.py` and `paai_queue_link.py` must sit beside it on `NUKE_PATH` / `~/.nuke`.

Alternatively add the whole `nuke_paai_pipeline` folder to `NUKE_PATH`.

Coming soon: show-level EXR colorspace agreement.

## Render Queue

Submitters talk to a **running** queue over HTTP via bundled `paai_queue_link.py` (no `paai_render_queue` Python import). Start the queue with `run_queue.bat` / `python -m paai_render_queue`. The optional **Render Queue path** field accepts a discovery folder or a URL.

## Naming table

| Concept | Nuke knob | show_config / files |
|--------|-----------|---------------------|
| version | `pl_version` | folder `v###` |
| claim | `pl_claim` | `.claim` |
| allow overwrite | `pl_allow_overwrite` | `allow_overwrite` (legacy `confirm_overwrite`) |
| start frame | script + show | `start_frame` |
| queue path | submit dialog | `render_queue_path` (folder or URL) |
| type | `pl_type` | `types.txt` / `default_type` |
| name | `pl_name` | folder under type (`DEFAULT_NAME=main`) |
| sequence / shot | `pl_sequence` / `pl_shot` | prefs `sequence` (legacy `seq`) |

Backward compat: the old folder name `nuke_pipeline_write` still imports via a shim.
