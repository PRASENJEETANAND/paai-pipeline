# PAAI Pipeline — ComfyUI

PAAI = Prasenjeet Anand Artist Interface

Custom nodes **PAAI Load** / **PAAI Write** under the **PAAI Pipeline** category, plus a Render Browser button.

Copy this folder into `ComfyUI/custom_nodes/`, then install requirements and restart.

Coming soon: show-level EXR colorspace agreement.

## Naming table

| Concept | ComfyUI input | show_config / files |
|--------|---------------|---------------------|
| version | `version` | folder `v###` |
| claim | `claim` | `.claim` |
| allow overwrite | `allow_overwrite` | `allow_overwrite` (legacy `confirm_overwrite`) |
| start frame | `start_frame` | `start_frame` |
| queue path | Render Queue path (UI / prefs) | `render_queue_path` |
| type | `type` | `types.txt` / `default_type` |
| name | `name` | folder under type (`DEFAULT_NAME=main`) |
| sequence / shot | `sequence` / `shot` | prefs `sequence` (legacy `seq`) |

## Render Queue

Discovery and submit use bundled `paai_queue_link.py` (no `paai_render_queue` import). Start the queue with `run_queue.bat`.
