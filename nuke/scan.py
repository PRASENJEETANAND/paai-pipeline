"""Disk scanning for the Render Browser and node dropdowns. Qt/nuke free."""
import os
import re
try:
    from . import pipeline_config as cfg
except ImportError:
    import pipeline_config as cfg

SEQ_RE = re.compile(r"^(.*?)(\d+)\.(\w+)$")
MOVIE_EXTS = {"mov", "mp4", "mxf", "avi"}
SKIP_FILES = {cfg.NOTE_FILE}


def find_sequences(folder):
    """Image sequences and single files in a version folder.
    Returns list of (path, first, last, count); first/last are None for singles."""
    if not folder or not os.path.isdir(folder):
        return []
    groups, singles = {}, []
    for f in sorted(os.listdir(folder)):
        if f in SKIP_FILES or f.startswith(".") or not os.path.isfile(os.path.join(folder, f)):
            continue
        m = SEQ_RE.match(f)
        if m and m.group(3).lower() not in MOVIE_EXTS:
            head, num, ext = m.groups()
            groups.setdefault((head, len(num), ext), []).append(int(num))
        elif "." in f:
            singles.append(f)
    out = [("%s/%s%s.%s" % (folder, head, "#" * pad, ext), min(fr), max(fr), len(fr))
           for (head, pad, ext), fr in groups.items()]
    out += [("%s/%s" % (folder, f), None, None, 1) for f in singles]
    return out


def scan_tree(root):
    return cfg.list_shots(root)


def scan_renders(root):
    """Yield render dicts for every version under root."""
    render_dir = cfg.render_subdir(root)
    for seq in cfg.list_dirs(root):
        for shot in cfg.list_dirs(os.path.join(root, seq)):
            rroot = os.path.join(root, seq, shot, render_dir)
            for rtype in cfg.list_dirs(rroot):
                tdir = os.path.join(rroot, rtype)
                cands = []
                for sub in cfg.list_dirs(tdir):
                    if cfg.is_version(sub):
                        cands.append(("main", sub, os.path.join(tdir, sub)))
                    else:
                        cands += [(sub, v, os.path.join(tdir, sub, v))
                                  for v in cfg.list_dirs(os.path.join(tdir, sub)) if cfg.is_version(v)]
                for name, ver, vdir in cands:
                    note = cfg.read_note(vdir)
                    for pattern, first, last, count in find_sequences(vdir):
                        yield dict(seq=seq, shot=shot, type=rtype, name=name, version=ver,
                                   first=first, last=last, count=count,
                                   path=cfg.norm_path(pattern), folder=cfg.norm_path(vdir),
                                   note=note.get("note", ""), user=note.get("user", ""),
                                   date=note.get("date", ""))


def type_dir(root, seq, shot, rtype, name="main"):
    name = (name or cfg.DEFAULT_NAME).strip().replace(" ", "_") or cfg.DEFAULT_NAME
    return cfg.join_path(cfg.norm_path(root), seq, shot, cfg.render_subdir(root), rtype, name)


def existing_versions(root, seq, shot, rtype, name="main"):
    d = type_dir(root, seq, shot, rtype, name)
    return sorted((x for x in cfg.list_dirs(d) if cfg.is_version(x)),
                  key=lambda v: int(v[1:]), reverse=True)


def next_version(root, seq, shot, rtype, name="main"):
    vers = existing_versions(root, seq, shot, rtype, name)
    return "v%03d" % (int(vers[0][1:]) + 1 if vers else 1)


def build_path(root, seq, shot, rtype, name, ver, ext, frame_token=".####"):
    """Full file pattern for a render."""
    name = (name or cfg.DEFAULT_NAME).strip().replace(" ", "_") or cfg.DEFAULT_NAME
    ext = (ext or "exr").lstrip(".").lower()
    if ext in ("jpeg",):
        ext = "jpg"
    if ext in ("tiff",):
        ext = "tif"
    tag = "%s_%s" % (rtype, name)
    frames = "" if ext in MOVIE_EXTS else frame_token
    fname = "%s_%s_%s_%s%s.%s" % (seq, shot, tag, ver, frames, ext)
    return cfg.join_path(type_dir(root, seq, shot, rtype, name), ver, fname)


def resolve_frame_files(pattern):
    """Expand a #### pattern into sorted list of (frame_num, filepath). Single files -> [(None, path)]."""
    pattern = (pattern or "").replace("\\", "/")
    if "#" not in pattern:
        return [(None, pattern)] if os.path.isfile(pattern) else []
    folder = os.path.dirname(pattern)
    base = os.path.basename(pattern)
    # turn name.####.exr into regex
    i = base.find("#")
    j = i
    while j < len(base) and base[j] == "#":
        j += 1
    pad = j - i
    head, tail = base[:i], base[j:]
    rx = re.compile("^" + re.escape(head) + r"(\d{" + str(pad) + r",})" + re.escape(tail) + "$")
    out = []
    if not os.path.isdir(folder):
        return out
    for f in sorted(os.listdir(folder)):
        m = rx.match(f)
        if m:
            out.append((int(m.group(1)), os.path.join(folder, f)))
    return out
