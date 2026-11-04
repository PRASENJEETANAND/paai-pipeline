"""Shared show settings for the PAAI pipeline (Nuke / ComfyUI / Blender compatible).

Per-show settings live in <SHOW ROOT>/showset/config/ as .txt files (created automatically):
    show_config.txt   render_subdir, allow_overwrite (legacy: confirm_overwrite),
                      start_frame, render_queue_path, default_type, ...
    types.txt         one render type per line:  name  ext  [named]
    shots.txt         one shot per line:          SEQ/SHOT
    names.txt         one name per line:          TYPE/NAME

App identity comes from sibling app_id.py (APP_NAME). Prefs: Nuke ~/.nuke/; others ~/.paai/<app>/.
Coming soon: show-level EXR colorspace agreement.
"""
import os
import socket
import getpass
import datetime
import json

DEFAULT_ROOT  = os.environ.get("PIPELINE_ROOT", "")
RENDER_SUBDIR = "paai"
IGNORE        = {".git", "_trash", "__pycache__", "showset"}
START_FRAME_DEFAULT = 1001
DEFAULT_NAME = "main"
CONFIRM_OVERWRITE = True  # legacy alias for allow_overwrite default
CLAIM_FILE = ".claim"
NOTE_FILE = "version_note.json"
MOVIE_EXTS = {"mov", "mp4", "mxf", "avi"}

RENDER_TYPES = {
    "precomp": "exr",
    "final":   "exr",
    "element": "exr",
    "plate":   "exr",
    "comfyui": "png",
    "cg_render": "exr",
}
NAMED_TYPES = {"element", "comfyui"}

# Resulting layout:
#   <ROOT>/<SEQ>/<SHOT>/paai/<type>/<name>/v###/<SEQ>_<SHOT>_<type>_<name>_v###.####.<ext>

# --------------------------------------------------------------------------- paths
def norm_path(p):
    """Accept / or \\; return forward-slash path (Nuke-friendly) without collapsing UNC leading slashes wrongly."""
    if p is None:
        return ""
    p = str(p).strip().replace("\\", "/")
    # keep drive letters; collapse duplicate slashes except leading // for UNC
    if p.startswith("//"):
        body = p[2:]
        while "//" in body:
            body = body.replace("//", "/")
        return "//" + body
    while "//" in p:
        p = p.replace("//", "/")
    return p


def join_path(*parts):
    raw = [norm_path(p) for p in parts if p is not None and str(p).strip() != ""]
    if not raw:
        return ""
    abs_unix = raw[0].startswith("/")
    abs_unc = raw[0].startswith("//")
    abs_win = len(raw[0]) >= 2 and raw[0][1] == ":"
    cleaned = []
    for i, p in enumerate(raw):
        if i == 0 and (abs_unix or abs_unc or abs_win):
            cleaned.append(p.rstrip("/"))
        else:
            cleaned.append(p.strip("/"))
    if abs_unc:
        body = cleaned[0][2:].strip("/")
        rest = [p for p in cleaned[1:] if p]
        return "//" + "/".join([body] + rest if body else rest)
    if abs_win:
        drive = cleaned[0][:2]
        rest0 = cleaned[0][2:].strip("/")
        rest = ([rest0] if rest0 else []) + [p for p in cleaned[1:] if p]
        return drive + ("/" + "/".join(rest) if rest else "/")
    if abs_unix:
        rest = [cleaned[0].lstrip("/")] + [p for p in cleaned[1:] if p]
        return "/" + "/".join([p for p in rest if p])
    return "/".join([p for p in cleaned if p])


def list_dirs(path):
    path = norm_path(path)
    if not path or not os.path.isdir(path):
        return []
    return sorted(d for d in os.listdir(path)
                  if os.path.isdir(os.path.join(path, d))
                  and not d.startswith(".") and d not in IGNORE)


def is_version(name):
    return bool(name) and len(name) > 1 and name[0] == "v" and name[1:].isdigit()


# --------------------------------------------------------------------------- notes
def read_note(version_dir):
    p = os.path.join(norm_path(version_dir), NOTE_FILE)
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return {}


def write_note(version_dir, note="", source="", frames="", format="", bit_depth="",
               compression="", host="", user="", **extra):
    """Unified version_note.json schema used by Nuke / ComfyUI / Blender."""
    version_dir = norm_path(version_dir)
    data = read_note(version_dir)
    data.update(extra)
    def _keep(val, key):
        # Empty or None means keep the existing value (browser note-only edits).
        if val is None or val == "":
            return data.get(key, "")
        return val

    data.update({
        "note": note if note is not None else data.get("note", ""),
        "source": source or data.get("source", ""),
        "user": user or getpass.getuser(),
        "host": host or socket.gethostname(),
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),  # legacy display
        "frames": _keep(frames, "frames"),
        "format": _keep(format, "format"),
        "bit_depth": _keep(bit_depth, "bit_depth"),
        "compression": _keep(compression, "compression"),
    })
    if not os.path.isdir(version_dir):
        os.makedirs(version_dir)
    with open(os.path.join(version_dir, NOTE_FILE), "w") as f:
        json.dump(data, f, indent=2)
    return data


# --------------------------------------------------------------------------- prefs
# APP_NAME comes from per-pack app_id.py so this file stays byte-identical across packs.
try:
    from .app_id import APP_NAME  # package import (ComfyUI / Blender)
except Exception:
    try:
        from app_id import APP_NAME  # flat NUKE_PATH import
    except Exception:
        APP_NAME = "nuke"
_LEGACY_NUKE_PREFS = os.path.join(os.path.expanduser("~"), ".nuke", "pipeline_prefs.json")


def _prefs_path():
    if APP_NAME == "nuke":
        return _LEGACY_NUKE_PREFS
    d = os.path.join(os.path.expanduser("~"), ".paai", APP_NAME)
    return os.path.join(d, "pipeline_prefs.json")


PREFS_FILE = _prefs_path()  # evaluated at import; packs may reassign APP_NAME then refresh


def _migrate_prefs_if_needed(dest):
    if os.path.isfile(dest):
        return
    # migrate from ~/.nuke if present
    if dest != _LEGACY_NUKE_PREFS and os.path.isfile(_LEGACY_NUKE_PREFS):
        try:
            d = os.path.dirname(dest)
            if not os.path.isdir(d):
                os.makedirs(d)
            import shutil
            shutil.copy2(_LEGACY_NUKE_PREFS, dest)
        except Exception:
            pass


def load_prefs():
    path = _prefs_path()
    _migrate_prefs_if_needed(path)
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save_prefs(**values):
    path = _prefs_path()
    data = load_prefs()
    values = dict(values)
    # Canonical key is "sequence"; accept legacy "seq" and write both for a while.
    if "seq" in values and "sequence" not in values:
        values["sequence"] = values["seq"]
    if "sequence" in values:
        values["seq"] = values["sequence"]  # legacy alias for older UIs
    data.update({k: v for k, v in values.items() if v is not None})
    try:
        d = os.path.dirname(path)
        if not os.path.isdir(d):
            os.makedirs(d)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def prefs_sequence(prefs=None):
    """Read sequence from prefs, accepting both sequence and legacy seq."""
    prefs = prefs if prefs is not None else load_prefs()
    return (prefs.get("sequence") or prefs.get("seq") or "")


def start_root():
    return load_prefs().get("root") or DEFAULT_ROOT


# ====================================================================== show config (.txt)
SHOWSET_DIR = "showset"
CONFIG_DIR  = "config"
DEFAULT_TYPES = [("precomp", "exr", False), ("final", "exr", False), ("element", "exr", True),
                 ("plate", "exr", False), ("comfyui", "png", True), ("cg_render", "exr", False)]


def ensure_config(root):
    return config_dir(root, create=True)


def config_dir(root, create=False):
    if not root:
        return ""
    root = norm_path(root)
    d = os.path.join(root, SHOWSET_DIR, CONFIG_DIR)
    if create and os.path.isdir(root):
        if not os.path.isdir(d):
            os.makedirs(d)
        _write_defaults(d)
    return d


def _write_defaults(d):
    p = os.path.join(d, "show_config.txt")
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write(
                "# Show settings: key = value\n"
                "# allow_overwrite: warn/block when writing into a version that already has frames\n"
                "# (confirm_overwrite is a legacy alias for the same setting)\n"
                "# default_type: optional show default; if empty each app keeps its own default\n"
                "render_subdir = %s\n"
                "allow_overwrite = %s\n"
                "start_frame = %d\n"
                "render_queue_path = \n"
                "default_type = \n"
                % (RENDER_SUBDIR, str(not CONFIRM_OVERWRITE).lower(), START_FRAME_DEFAULT)
            )
    else:
        # ensure new keys exist without clobbering
        try:
            text = open(p).read()
            additions = []
            if "start_frame" not in text:
                additions.append("start_frame = %d\n" % START_FRAME_DEFAULT)
            if "render_queue_path" not in text:
                additions.append("render_queue_path = \n")
            if "allow_overwrite" not in text and "confirm_overwrite" not in text:
                additions.append("allow_overwrite = %s\n" % str(not CONFIRM_OVERWRITE).lower())
            if "default_type" not in text:
                additions.append("default_type = \n")
            if additions:
                with open(p, "a") as f:
                    f.write("".join(additions))
        except Exception:
            pass
    p = os.path.join(d, "types.txt")
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write("# Render types: name  ext  [named]   (named = asks for an element name)\n")
            for name, ext, named in DEFAULT_TYPES:
                f.write("%-10s %-4s%s\n" % (name, ext, "  named" if named else ""))
    p = os.path.join(d, "names.txt")
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write("# Render names: TYPE/NAME, one per line (each name gets its own versions)\n")
            for name, _, _ in DEFAULT_TYPES:
                f.write("%s/%s\n" % (name, DEFAULT_NAME))
    p = os.path.join(d, "shots.txt")
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write("# Shots: SEQUENCE/SHOT, one per line\n")


def _lines(path):
    try:
        with open(path) as f:
            return [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    except Exception:
        return []


def show_settings(root):
    """Read show_config.txt.

    Overwrite policy:
      - Preferred key: allow_overwrite (False = warn/block unless the artist opts in).
      - Legacy key: confirm_overwrite (True = warn/block). Mapped to allow_overwrite = not confirm.
    Both keys are exposed on the returned dict for callers.
    """
    out = {
        "render_subdir": RENDER_SUBDIR,
        "allow_overwrite": not CONFIRM_OVERWRITE,
        "confirm_overwrite": CONFIRM_OVERWRITE,
        "start_frame": START_FRAME_DEFAULT,
        "render_queue_path": "",
        "default_type": "",
    }
    saw_allow = False
    saw_confirm = False
    for l in _lines(os.path.join(config_dir(root), "show_config.txt")):
        if "=" in l:
            k, v = [x.strip() for x in l.split("=", 1)]
            if k == "allow_overwrite":
                out["allow_overwrite"] = v.lower() in ("1", "true", "yes", "on")
                saw_allow = True
            elif k == "confirm_overwrite":
                out["confirm_overwrite"] = v.lower() in ("1", "true", "yes", "on")
                saw_confirm = True
            elif k == "start_frame":
                try:
                    out[k] = int(v)
                except Exception:
                    out[k] = START_FRAME_DEFAULT
            else:
                out[k] = v
    # Keep the two overwrite keys in sync (prefer allow_overwrite when both set).
    if saw_allow and not saw_confirm:
        out["confirm_overwrite"] = not out["allow_overwrite"]
    elif saw_confirm and not saw_allow:
        out["allow_overwrite"] = not out["confirm_overwrite"]
    elif saw_allow and saw_confirm:
        out["confirm_overwrite"] = not out["allow_overwrite"]
    return out


def default_type(root, fallback=""):
    """Show-level default render type, or fallback (app-specific) when unset."""
    v = (show_settings(root).get("default_type") or "").strip()
    return v or (fallback or "")


def render_subdir(root):
    return show_settings(root)["render_subdir"]


def start_frame(root):
    try:
        return int(show_settings(root).get("start_frame") or START_FRAME_DEFAULT)
    except Exception:
        return START_FRAME_DEFAULT


def render_queue_path(root):
    """Show-level path to paai_render_queue install and/or discovery hints."""
    return norm_path(show_settings(root).get("render_queue_path") or "")


def set_show_setting(root, key, value):
    """Update or append a key in show_config.txt."""
    d = ensure_config(root)
    p = os.path.join(d, "show_config.txt")
    lines = []
    try:
        with open(p) as f:
            lines = f.readlines()
    except Exception:
        lines = ["# Show settings: key = value\n"]
    key = key.strip()
    found = False
    out = []
    for line in lines:
        raw = line.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            k = raw.split("=", 1)[0].strip()
            if k == key:
                out.append("%s = %s\n" % (key, value))
                found = True
                continue
        out.append(line if line.endswith("\n") else line + "\n")
    if not found:
        out.append("%s = %s\n" % (key, value))
    with open(p, "w") as f:
        f.writelines(out)


def _types(root):
    rows = []
    for l in _lines(os.path.join(config_dir(root), "types.txt")):
        parts = l.split()
        rows.append((parts[0], parts[1] if len(parts) > 1 else "exr",
                     len(parts) > 2 and parts[2].lower() == "named"))
    return rows or list(DEFAULT_TYPES)


def render_types(root):
    return [t[0] for t in _types(root)]


def type_ext(root, rtype):
    return {t[0]: t[1] for t in _types(root)}.get(rtype, "exr")


def is_named(root, rtype):
    return {t[0]: t[2] for t in _types(root)}.get(rtype, False)


def add_type(root, name, ext="exr", named=False):
    name = name.strip().replace(" ", "_")
    if not name or name in render_types(root):
        return False
    with open(os.path.join(ensure_config(root), "types.txt"), "a") as f:
        f.write("%-10s %-4s%s\n" % (name, ext.strip(".") or "exr", "  named" if named else ""))
    return True


def list_shots(root):
    root = norm_path(root)
    tree = {}
    for seq in list_dirs(root):
        tree[seq] = set(list_dirs(os.path.join(root, seq)))
    for l in _lines(os.path.join(config_dir(root), "shots.txt")):
        if "/" in l:
            seq, shot = [x.strip() for x in l.split("/", 1)]
            tree.setdefault(seq, set()).add(shot)
    return {k: sorted(v) for k, v in sorted(tree.items())}


def add_shot(root, seq, shot, make_folders=True):
    root = norm_path(root)
    seq, shot = seq.strip().replace(" ", "_"), shot.strip().replace(" ", "_")
    if not seq or not shot:
        return False
    path = os.path.join(ensure_config(root), "shots.txt")
    existing = set(_lines(path))
    if "%s/%s" % (seq, shot) not in existing:
        with open(path, "a") as f:
            f.write("%s/%s\n" % (seq, shot))
    if make_folders:
        d = os.path.join(root, seq, shot, render_subdir(root))
        if not os.path.isdir(d):
            os.makedirs(d)
    return True


def list_names(root, found=None):
    tree = {t: set() for t in render_types(root)}
    for l in _lines(os.path.join(config_dir(root), "names.txt")):
        if "/" in l:
            t, n = [x.strip() for x in l.split("/", 1)]
            tree.setdefault(t, set()).add(n)
    for t, n in (found or []):
        tree.setdefault(t, set()).add(n or DEFAULT_NAME)
    return {t: sorted(v) for t, v in tree.items()}


def add_name(root, rtype, name):
    rtype, name = rtype.strip(), name.strip().replace(" ", "_")
    if not rtype or not name:
        return False
    path = os.path.join(ensure_config(root), "names.txt")
    if "%s/%s" % (rtype, name) not in set(_lines(path)):
        with open(path, "a") as f:
            f.write("%s/%s\n" % (rtype, name))
    return True


# --------------------------------------------------------------------------- version claim / frames
def version_has_frames(version_dir):
    """True if version folder contains any render files (not just note/claim)."""
    version_dir = norm_path(version_dir)
    if not version_dir or not os.path.isdir(version_dir):
        return False
    skip = {NOTE_FILE, CLAIM_FILE}
    for f in os.listdir(version_dir):
        if f in skip or f.startswith("."):
            continue
        fp = os.path.join(version_dir, f)
        if os.path.isfile(fp):
            return True
        if os.path.isdir(fp) and any(os.path.isfile(os.path.join(fp, x)) for x in os.listdir(fp)[:20]):
            return True
    return False


def read_claim(version_dir):
    p = os.path.join(norm_path(version_dir), CLAIM_FILE)
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return {}


def claim_version(parent_dir, preferred, source_app, max_tries=50):
    """Atomically reserve a version folder under parent_dir.

    preferred: 'New' or 'v003'. When claiming, mkdir the folder + write .claim.
    If preferred exists / is claimed by another host+app concurrently, bump.
    Returns (version, version_dir, claimed_bool).
    """
    parent_dir = norm_path(parent_dir)
    if not parent_dir:
        raise ValueError("claim_version: empty parent_dir")
    if not os.path.isdir(parent_dir):
        os.makedirs(parent_dir)

    def _existing():
        return sorted((d for d in list_dirs(parent_dir) if is_version(d)),
                      key=lambda v: int(v[1:]), reverse=True)

    def _next_after(vers):
        return "v%03d" % (int(vers[0][1:]) + 1 if vers else 1)

    user = getpass.getuser()
    host = socket.gethostname()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    claim_body = {
        "app": source_app or APP_NAME,
        "user": user,
        "host": host,
        "time": now,
    }

    start = preferred
    if not start or start == "New" or not is_version(start):
        start = _next_after(_existing())

    ver = start
    for _ in range(max_tries):
        vdir = os.path.join(parent_dir, ver)
        try:
            os.mkdir(vdir)  # atomic claim of the directory itself
        except FileExistsError:
            # folder exists — if empty of frames and our claim or no claim, reuse when preferred exact?
            # Spec: if folder already exists or claimed by someone else, bump
            ver = "v%03d" % (int(ver[1:]) + 1)
            continue
        except OSError:
            ver = "v%03d" % (int(ver[1:]) + 1)
            continue
        # write claim file
        try:
            with open(os.path.join(vdir, CLAIM_FILE), "w") as f:
                json.dump(claim_body, f, indent=2)
        except Exception:
            pass
        return ver, norm_path(vdir), True

    raise RuntimeError("Could not claim a free version under %s" % parent_dir)


def next_version_name(parent_dir):
    vers = sorted((d for d in list_dirs(parent_dir) if is_version(d)),
                  key=lambda v: int(v[1:]), reverse=True)
    return "v%03d" % (int(vers[0][1:]) + 1 if vers else 1)
