#!/usr/bin/env python3
"""PAAI show create / check — stdlib only.

Byte-identical copy lives in tools/ and in each DCC pack (nuke/, blender/, comfyui/).
Conventions match pipeline_config.py:
  <ROOT>/showset/config/{show_config,types,shots,names}.txt
  <ROOT>/<SEQ>/<SHOT>/paai/<type>/[<name>/]v###/...
"""
from __future__ import print_function

import argparse
import os
import re
import sys

RENDER_SUBDIR = "paai"
SHOWSET_DIR = "showset"
CONFIG_DIR = "config"
START_FRAME_DEFAULT = 1001
DEFAULT_NAME = "main"
CLAIM_FILE = ".claim"
NOTE_FILE = "version_note.json"

DEFAULT_TYPES = [
    ("precomp", "exr", False),
    ("final", "exr", False),
    ("element", "exr", True),
    ("plate", "exr", False),
    ("comfyui", "png", True),
    ("cg_render", "exr", False),
]

VERSION_RE = re.compile(r"^v\d{3,}$")
# SEQ_SHOT_type[_name]_v###.####.ext  OR still/movie without frames
FILE_RE = re.compile(
    r"^(?P<seq>[^_]+)_(?P<shot>[^_]+)_(?P<tag>.+?)_(?P<ver>v\d{3,})"
    r"(?:\.(?P<frame>\d+))?\.(?P<ext>\w+)$"
)
SEQ_FRAME_RE = re.compile(r"^(.*?)(\d+)\.(\w+)$")


def norm_path(p):
    if p is None:
        return ""
    return str(p).strip().replace("\\", "/")


def config_dir(root):
    return os.path.join(norm_path(root), SHOWSET_DIR, CONFIG_DIR)


def _write_if_missing(path, content):
    if os.path.exists(path):
        return False
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w") as f:
        f.write(content)
    return True


def _parse_shots_arg(seq, shots_csv):
    """SQ010 + SH010,SH020 -> [(SQ010, SH010), ...]"""
    out = []
    seq = (seq or "").strip().replace(" ", "_")
    if not seq:
        return out
    for s in (shots_csv or "").split(","):
        s = s.strip().replace(" ", "_")
        if s:
            out.append((seq, s))
    return out


def _parse_seq_shots_token(token):
    """SQ010:SH010,SH020 -> list of (seq, shot)."""
    token = (token or "").strip()
    if not token:
        return []
    if ":" in token:
        seq, rest = token.split(":", 1)
        return _parse_shots_arg(seq, rest)
    if "/" in token:
        seq, shot = token.split("/", 1)
        return [(seq.strip().replace(" ", "_"), shot.strip().replace(" ", "_"))]
    return []


def _load_shots_file(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "/" in line:
                a, b = line.split("/", 1)
                out.append((a.strip().replace(" ", "_"), b.strip().replace(" ", "_")))
            else:
                parts = _parse_seq_shots_token(line)
                out.extend(parts)
    return out


def create_show(root, pairs, quiet=False):
    """Create showset/config + shot/paai folders. Idempotent; never overwrites config."""
    root = norm_path(os.path.abspath(os.path.expanduser(root)))
    if not root:
        raise SystemExit("create: --root is required")
    if not os.path.isdir(root):
        os.makedirs(root)

    cfg = config_dir(root)
    if not os.path.isdir(cfg):
        os.makedirs(cfg)

    created = []
    show_config = os.path.join(cfg, "show_config.txt")
    if _write_if_missing(
        show_config,
        "# Show settings: key = value\n"
        "# allow_overwrite: warn/block when writing into a version that already has frames\n"
        "# (confirm_overwrite is a legacy alias for the same setting)\n"
        "# default_type: optional show default; if empty each app keeps its own default\n"
        "render_subdir = %s\n"
        "allow_overwrite = false\n"
        "start_frame = %d\n"
        "render_queue_path = \n"
        "default_type = \n" % (RENDER_SUBDIR, START_FRAME_DEFAULT),
    ):
        created.append("show_config.txt")

    types_path = os.path.join(cfg, "types.txt")
    if _write_if_missing(
        types_path,
        "# Render types: name  ext  [named]   (named = asks for an element name)\n"
        + "".join(
            "%-10s %-4s%s\n" % (n, e, "  named" if named else "")
            for n, e, named in DEFAULT_TYPES
        ),
    ):
        created.append("types.txt")

    names_path = os.path.join(cfg, "names.txt")
    if _write_if_missing(
        names_path,
        "# Render names: TYPE/NAME, one per line (each name gets its own versions)\n"
        + "".join("%s/%s\n" % (n, DEFAULT_NAME) for n, _, _ in DEFAULT_TYPES),
    ):
        created.append("names.txt")

    shots_path = os.path.join(cfg, "shots.txt")
    if not os.path.exists(shots_path):
        with open(shots_path, "w") as f:
            f.write("# Shots: SEQUENCE/SHOT, one per line\n")
        created.append("shots.txt")

    # Merge new shots into shots.txt without removing existing
    existing = set()
    with open(shots_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "/" in line:
                existing.add(line)
    added_shots = []
    with open(shots_path, "a") as f:
        for seq, shot in pairs:
            key = "%s/%s" % (seq, shot)
            if key not in existing:
                f.write("%s\n" % key)
                existing.add(key)
                added_shots.append(key)

    # Folders
    folders = []
    for seq, shot in pairs:
        d = os.path.join(root, seq, shot, RENDER_SUBDIR)
        if not os.path.isdir(d):
            os.makedirs(d)
            folders.append(norm_path(d))

    if not quiet:
        print("PAAI show create")
        print("  root: %s" % root)
        print("  config: %s" % cfg)
        if created:
            print("  new config files: %s" % ", ".join(created))
        else:
            print("  config files: unchanged (already present)")
        if added_shots:
            print("  shots added: %s" % ", ".join(added_shots))
        else:
            print("  shots: no new entries")
        if folders:
            print("  folders created: %d" % len(folders))
        else:
            print("  folders: already present")
        print("OK")
    return {
        "root": root,
        "created_config": created,
        "added_shots": added_shots,
        "folders": folders,
    }


def _read_lines(path):
    try:
        with open(path) as f:
            return [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    except Exception:
        return []


def _read_types(cfg):
    rows = []
    for l in _read_lines(os.path.join(cfg, "types.txt")):
        parts = l.split()
        if not parts:
            continue
        rows.append(parts[0])
    return rows or [t[0] for t in DEFAULT_TYPES]


def _list_dirs(path):
    if not path or not os.path.isdir(path):
        return []
    return sorted(
        d
        for d in os.listdir(path)
        if os.path.isdir(os.path.join(path, d))
        and not d.startswith(".")
        and d not in {".git", "_trash", "__pycache__", SHOWSET_DIR}
    )


def _find_sequences(folder):
    if not folder or not os.path.isdir(folder):
        return []
    groups = {}
    for f in sorted(os.listdir(folder)):
        if f in {NOTE_FILE, CLAIM_FILE} or f.startswith("."):
            continue
        fp = os.path.join(folder, f)
        if not os.path.isfile(fp):
            continue
        m = SEQ_FRAME_RE.match(f)
        if m:
            head, num, ext = m.groups()
            groups.setdefault((head, len(num), ext), []).append(int(num))
    out = []
    for (head, pad, ext), fr in groups.items():
        fr = sorted(fr)
        gaps = [a + 1 for a, b in zip(fr, fr[1:]) if b > a + 1]
        out.append((head, fr[0], fr[-1], len(fr), gaps))
    return out


def check_show(root, quiet=False):
    """Validate show layout. Returns (exit_code, lines). 0=OK, 1=WARN, 2=ERROR."""
    root = norm_path(os.path.abspath(os.path.expanduser(root)))
    lines = []
    errors = 0
    warns = 0

    def err(msg):
        nonlocal errors
        errors += 1
        lines.append("ERROR  %s" % msg)

    def warn(msg):
        nonlocal warns
        warns += 1
        lines.append("WARN   %s" % msg)

    def ok(msg):
        lines.append("OK     %s" % msg)

    if not root or not os.path.isdir(root):
        err("root not found: %s" % root)
        return 2, lines

    cfg = config_dir(root)
    required = ["show_config.txt", "types.txt", "shots.txt", "names.txt"]
    for name in required:
        p = os.path.join(cfg, name)
        if not os.path.isfile(p):
            err("missing config file: %s" % p)
        else:
            ok("found %s" % name)

    # show_config keys
    sc = os.path.join(cfg, "show_config.txt")
    if os.path.isfile(sc):
        text = open(sc).read()
        for key in ("render_subdir", "start_frame", "render_queue_path", "default_type"):
            if key not in text:
                warn("show_config.txt missing key: %s" % key)
        if "allow_overwrite" not in text and "confirm_overwrite" not in text:
            warn("show_config.txt missing allow_overwrite (or legacy confirm_overwrite)")
        else:
            ok("show_config overwrite policy present")

    types = _read_types(cfg) if os.path.isdir(cfg) else []
    known = set(types)
    for t, _, _ in DEFAULT_TYPES:
        if t not in known:
            warn("default type %r not in types.txt" % t)

    # shots.txt vs folders
    shot_pairs = []
    for l in _read_lines(os.path.join(cfg, "shots.txt")):
        if "/" in l:
            a, b = [x.strip() for x in l.split("/", 1)]
            shot_pairs.append((a, b))
    disk_pairs = []
    for seq in _list_dirs(root):
        for shot in _list_dirs(os.path.join(root, seq)):
            disk_pairs.append((seq, shot))

    shot_set = set(shot_pairs)
    disk_set = set(disk_pairs)
    for seq, shot in sorted(shot_set - disk_set):
        warn("shot in shots.txt has no folder: %s/%s" % (seq, shot))
    for seq, shot in sorted(disk_set - shot_set):
        warn("shot folder not listed in shots.txt: %s/%s" % (seq, shot))
    if shot_set or disk_set:
        ok("shots: %d in shots.txt, %d folders on disk" % (len(shot_set), len(disk_set)))

    # Walk renders
    for seq, shot in sorted(disk_set or shot_set):
        rroot = os.path.join(root, seq, shot, RENDER_SUBDIR)
        if not os.path.isdir(rroot):
            warn("missing paai folder: %s/%s/%s" % (seq, shot, RENDER_SUBDIR))
            continue
        for rtype in _list_dirs(rroot):
            if rtype not in known:
                warn("unknown render type folder: %s/%s/%s/%s" % (seq, shot, RENDER_SUBDIR, rtype))
            tdir = os.path.join(rroot, rtype)
            # versions directly or under name/
            cands = []
            for sub in _list_dirs(tdir):
                if VERSION_RE.match(sub):
                    cands.append((DEFAULT_NAME, sub, os.path.join(tdir, sub)))
                else:
                    for ver in _list_dirs(os.path.join(tdir, sub)):
                        if VERSION_RE.match(ver):
                            cands.append((sub, ver, os.path.join(tdir, sub, ver)))
                        elif not ver.startswith("."):
                            warn("misnamed version folder (want v###): %s" % os.path.join(tdir, sub, ver))
            for name, ver, vdir in cands:
                claim = os.path.join(vdir, CLAIM_FILE)
                frames = _find_sequences(vdir)
                files = [
                    f
                    for f in os.listdir(vdir)
                    if os.path.isfile(os.path.join(vdir, f))
                    and f not in {NOTE_FILE, CLAIM_FILE}
                    and not f.startswith(".")
                ]
                if os.path.isfile(claim) and not files:
                    warn("orphan .claim (no frames yet): %s" % norm_path(vdir))
                for f in files:
                    m = FILE_RE.match(f)
                    if not m:
                        # allow simple stills that still have v### in path via folder
                        if VERSION_RE.search(f) or SEQ_FRAME_RE.match(f):
                            continue
                        warn("filename does not match pattern: %s" % norm_path(os.path.join(vdir, f)))
                        continue
                    if m.group("seq") != seq or m.group("shot") != shot:
                        warn("filename seq/shot mismatch: %s" % f)
                    if m.group("ver") != ver:
                        warn("filename version mismatch folder=%s file=%s" % (ver, f))
                for head, first, last, count, gaps in frames:
                    if gaps:
                        warn(
                            "frame gaps in %s (%s): missing after %s"
                            % (norm_path(vdir), head, gaps[:8])
                        )

    status = "OK" if errors == 0 and warns == 0 else ("WARN" if errors == 0 else "ERROR")
    summary = "PAAI show check — %s  (errors=%d warns=%d)  root=%s" % (
        status, errors, warns, root,
    )
    lines.insert(0, summary)
    if not quiet:
        print("\n".join(lines))
    code = 0 if errors == 0 and warns == 0 else (1 if errors == 0 else 2)
    return code, lines


def create_and_check(root, pairs):
    create_show(root, pairs)
    return check_show(root)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(prog="paai_show", description="Create / check a PAAI show tree")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="Create showset/config and shot/paai folders")
    c.add_argument("--root", required=True, help="Show / project root")
    c.add_argument("--seq", default="", help="Sequence name, e.g. SQ010")
    c.add_argument("--shots", default="", help="Comma-separated shots, e.g. SH010,SH020")
    c.add_argument(
        "--seq-shots",
        action="append",
        default=[],
        help="SQ010:SH010,SH020 (repeatable)",
    )
    c.add_argument("--shots-file", default="", help="File with SEQ/SHOT or SEQ:SHOT,... lines")
    c.add_argument("-q", "--quiet", action="store_true")

    k = sub.add_parser("check", help="Validate show config and render layout")
    k.add_argument("--root", required=True, help="Show / project root")
    k.add_argument("-q", "--quiet", action="store_true")

    args = ap.parse_args(argv)
    if args.cmd == "create":
        pairs = []
        pairs += _parse_shots_arg(args.seq, args.shots)
        for tok in args.seq_shots:
            pairs += _parse_seq_shots_token(tok)
        if args.shots_file:
            pairs += _load_shots_file(args.shots_file)
        # de-dupe preserve order
        seen = set()
        uniq = []
        for p in pairs:
            if p not in seen and p[0] and p[1]:
                seen.add(p)
                uniq.append(p)
        if not uniq:
            print("create: provide --seq/--shots and/or --seq-shots and/or --shots-file", file=sys.stderr)
            return 2
        create_show(args.root, uniq, quiet=args.quiet)
        return 0
    if args.cmd == "check":
        code, _ = check_show(args.root, quiet=args.quiet)
        return code
    return 2


if __name__ == "__main__":
    sys.exit(main())
