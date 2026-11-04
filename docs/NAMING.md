# Naming table

| Concept | Nuke | ComfyUI | Blender | show_config / files |
|--------|------|---------|---------|---------------------|
| version | `pl_version` | `version` | `version` | folder `v###` |
| claim | `pl_claim` | `claim` | `claim` | `.claim` |
| allow overwrite | `pl_allow_overwrite` | `allow_overwrite` | `allow_overwrite` | `allow_overwrite` (legacy `confirm_overwrite`) |
| start frame | script + show | `start_frame` | scene + show | `start_frame` |
| queue path | submit dialog | UI / prefs | `render_queue_path` | `render_queue_path` (folder or URL) |
| type | `pl_type` | `type` | `render_type` | `types.txt` / `default_type` |
| name | `pl_name` | `name` | `name` | under type (`main` default) |
| sequence / shot | `pl_sequence` / `pl_shot` | `sequence` / `shot` | `sequence` / `shot` | prefs `sequence` (legacy `seq`) |

**PAAI** = Prasenjeet Anand Artist Interface.
