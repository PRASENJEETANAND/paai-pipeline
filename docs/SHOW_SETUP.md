# Show setup

## Layout

```
<ROOT>/
  showset/config/
    show_config.txt
    types.txt
    shots.txt
    names.txt
  <SEQ>/<SHOT>/paai/
    <type>/[<name>/]v###/
      <SEQ>_<SHOT>_<type>[_<name>]_v###.####.<ext>
      version_note.json
      .claim          # while Claim is on
```

## Create

```bash
python tools/paai_show.py create --root D:/SHOWS/MYSHOW \
  --seq SQ010 --shots SH010,SH020
# or
python tools/paai_show.py create --root D:/SHOWS/MYSHOW \
  --seq-shots SQ010:SH010,SH020 --seq-shots SQ020:SH010
```

Idempotent: existing config files are **never** overwritten; new shots are appended.

## Check

```bash
python tools/paai_show.py check --root D:/SHOWS/MYSHOW
echo %ERRORLEVEL%   # 0 OK, 1 WARN, 2 ERROR
```

Reports missing config/keys, shots.txt vs folders, unknown types, bad `v###` names, filename pattern mismatches, frame gaps, orphan `.claim` files.

## show_config.txt keys

| Key | Default | Meaning |
|-----|---------|---------|
| `render_subdir` | `paai` | Folder under each shot |
| `allow_overwrite` | `false` | Show policy; artists still need the per-write toggle |
| `confirm_overwrite` | legacy alias | `true` ≈ not allow_overwrite |
| `start_frame` | `1001` | Default frame numbering |
| `render_queue_path` | empty | Optional discovery folder or queue URL |
| `default_type` | empty | If set, preferred render type; else each app keeps its default |
