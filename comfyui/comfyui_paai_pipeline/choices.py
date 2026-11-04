"""Shared format / dropdown helpers for ComfyUI and Blender.

App-specific Blender codec maps live in choices_blender.py.
Identical bytes across packs.
"""
import os
try:
    from . import pipeline_config as cfg
    from . import scan
except ImportError:
    import pipeline_config as cfg
    import scan

NEW = "New"

FORMATS = {
    "exr": {
        "bit_depth": ["half", "float"],
        "compression": ["zip", "zips", "piz", "pxr24", "rle", "dwaa", "dwab", "none"],
    },
    "exr multilayer": {
        "bit_depth": ["half", "float"],
        "compression": ["zip", "zips", "piz", "pxr24", "rle", "dwaa", "dwab", "none"],
    },
    "png": {
        "bit_depth": ["8", "16"],
        # 0-100 scale (Blender); Comfy maps to zlib level via png_zlib_level
        "compression": ["level 15", "level 0", "level 50", "level 90", "level 100"],
    },
    "jpg": {
        "bit_depth": ["8"],
        "compression": ["quality 90", "quality 100", "quality 95", "quality 80", "quality 70"],
    },
    "tiff": {
        "bit_depth": ["8", "16", "float"],
        "compression": ["lzw", "deflate", "zip", "packbits", "none"],
    },
}
FILE_TYPES = list(FORMATS)


def all_values(key):
    out = []
    for f in FORMATS.values():
        for v in f[key]:
            if v not in out:
                out.append(v)
    return out


def fix_format(file_type, bit_depth, compression):
    f = FORMATS.get(file_type, FORMATS["exr"])
    bd = bit_depth if bit_depth in f["bit_depth"] else f["bit_depth"][0]
    co = compression if compression in f["compression"] else f["compression"][0]
    return bd, co


def ext_for(file_type):
    return {
        "exr": "exr", "exr multilayer": "exr",
        "png": "png", "jpg": "jpg", "tiff": "tif",
    }.get(file_type, "exr")


def png_zlib_level(compression):
    """Map shared 0-100 'level N' to zlib 0-9 for image writers."""
    try:
        n = int(str(compression).split()[-1])
    except Exception:
        n = 15
    return max(0, min(9, int(round(n * 9 / 100.0))))


def _pick(value, values):
    return value if value in values else (values[0] if values else "")


def dropdowns(root, sequence="", shot="", rtype="", name="", for_load=False):
    root = cfg.norm_path(root or "")
    if not root or not os.path.isdir(root):
        return None
    cfg.ensure_config(root)
    shots = cfg.list_shots(root)
    seq_list = list(shots)
    sequence = _pick(sequence, seq_list)
    shot_list = shots.get(sequence, [])
    shot = _pick(shot, shot_list)
    types = cfg.render_types(root)
    rtype = _pick(rtype, types)
    names = cfg.list_names(root).get(rtype, [cfg.DEFAULT_NAME]) or [cfg.DEFAULT_NAME]
    try:
        tdir = scan.type_dir(root, sequence, shot, rtype, cfg.DEFAULT_NAME)
        parent = os.path.dirname(tdir)
        on_disk = [d for d in cfg.list_dirs(parent) if not cfg.is_version(d)]
        for n in on_disk:
            if n not in names:
                names.append(n)
    except Exception:
        pass
    name = _pick(name, names)
    vers = scan.existing_versions(root, sequence, shot, rtype, name)
    return {
        "root": root,
        "sequences": seq_list,
        "shots": shot_list,
        "types": types,
        "names": names,
        "versions": vers if for_load else [NEW] + vers,
        "sequence": sequence,
        "shot": shot,
        "type": rtype,
        "name": name,
        "file_types": FILE_TYPES,
        "formats": FORMATS,
        "start_frame": cfg.start_frame(root),
        "render_queue_path": cfg.render_queue_path(root),
        "default_type": cfg.default_type(root, ""),
    }


def initial(for_load=False):
    """Lists for INPUT_TYPES, from the last used root."""
    d = None
    try:
        d = dropdowns(cfg.start_root() or "", for_load=for_load)
    except Exception:
        d = None
    if not d:
        return {"sequences": [""], "shots": [""],
                "types": ["comfyui", "precomp", "final", "element", "plate", "cg_render"],
                "names": [cfg.DEFAULT_NAME], "versions": [""] if for_load else [NEW],
                "start_frame": cfg.START_FRAME_DEFAULT, "render_queue_path": "",
                "default_type": ""}
    allshots = sorted({s for v in cfg.list_shots(d["root"]).values() for s in v}) or [""]
    d["shots"] = allshots
    return d
