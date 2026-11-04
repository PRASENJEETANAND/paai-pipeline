"""Apply PAAI panel settings onto Blender's scene.render filepath / image_settings."""
import os
import re
from . import pipeline_config as cfg
from . import scan
from . import choices_blender as choices


def resolve_version(root, seq, shot, rtype, name, version, locked=None, claim=False):
    """Return (version, is_new, version_dir)."""
    parent = scan.type_dir(root, seq, shot, rtype, name)
    if locked and cfg.is_version(locked):
        is_new = (version == choices.NEW or not version)
        return locked, is_new, cfg.join_path(parent, locked)
    version = version or choices.NEW
    is_new = version == choices.NEW or not version
    if claim:
        preferred = choices.NEW if is_new else version
        ver, vdir, _ = cfg.claim_version(parent, preferred, source_app="blender")
        return ver, True, vdir
    if is_new:
        ver = scan.next_version(root, seq, shot, rtype, name)
    else:
        ver = version
    return ver, is_new, cfg.join_path(parent, ver)


def build_output_path(props, locked_version=None, do_claim=None):
    root = cfg.norm_path((props.root or "").strip())
    seq = props.sequence or ""
    shot = props.shot or ""
    rtype = props.render_type or "cg_render"
    name = (props.name or cfg.DEFAULT_NAME).strip().replace(" ", "_") or cfg.DEFAULT_NAME
    if not root or not seq or not shot:
        return None, None, None, False, "pick root / sequence / shot"
    file_type = props.file_type or "exr"
    ext = choices.ext_for(file_type)
    locked = locked_version if locked_version is not None else getattr(props, "locked_version", "")
    claim = getattr(props, "claim", getattr(props, "claim_version", True)) if do_claim is None else do_claim
    # Only claim when locking for a real render (do_claim True); preview paths don't claim
    ver, is_new, vdir = resolve_version(
        root, seq, shot, rtype, name, props.version,
        locked=locked, claim=bool(claim and not locked and do_claim),
    )
    path = scan.build_path(root, seq, shot, rtype, name, ver, ext, frame_token=".####")
    info = ("NEW  %s | %s | %s_%s | %s" % (seq, shot, rtype, name, ver)
            if is_new else
            "OVERWRITE  %s | %s | %s_%s | %s" % (seq, shot, rtype, name, ver))
    return path, vdir, ver, is_new, info


def apply_image_settings(scene, props):
    file_type = props.file_type or "exr"
    bit_depth, compression = choices.fix_format(file_type, props.bit_depth, props.compression)
    fmt = choices.FORMATS[file_type]
    s = scene.render.image_settings
    s.file_format = fmt["blender_format"]
    depth = choices.BIT_TO_DEPTH.get(bit_depth, "16")
    try:
        s.color_depth = depth
    except Exception:
        pass
    if file_type in ("exr", "exr multilayer"):
        codec = choices.EXR_CODEC.get(compression, "ZIP")
        try:
            s.exr_codec = codec
        except Exception:
            pass
    elif file_type == "png":
        try:
            level = int(str(compression).split()[-1])
        except Exception:
            level = 15
        s.compression = max(0, min(100, level))
    elif file_type == "jpg":
        try:
            q = int(str(compression).split()[-1])
        except Exception:
            q = 90
        s.quality = max(0, min(100, q))
    elif file_type == "tiff":
        codec = choices.TIFF_CODEC.get(compression, "LZW")
        try:
            s.tiff_codec = codec
        except Exception:
            pass
    return bit_depth, compression


def expand_frame(path, frame):
    if not path or "#" not in path:
        return path
    return re.sub(r"#+", lambda m: "%0*d" % (len(m.group(0)), int(frame)), path)


def apply_to_scene(scene, create_dirs=False, expand_current_frame=False, do_claim=False):
    props = scene.paai
    path, vdir, ver, is_new, info = build_output_path(props, do_claim=do_claim)
    props.path_preview = path or ""
    props.path_info = info
    if not path:
        return None
    if create_dirs and vdir and not os.path.isdir(vdir):
        os.makedirs(vdir)
    apply_image_settings(scene, props)
    fp = path
    if expand_current_frame:
        fp = expand_frame(path, scene.frame_current)
    scene.render.filepath = fp
    # Persist show-level queue path if set on panel
    try:
        rq = getattr(props, "render_queue_path", "") or ""
        if rq and props.root:
            cfg.set_show_setting(props.root, "render_queue_path", cfg.norm_path(rq))
    except Exception:
        pass
    return fp


def check_overwrite_allowed(scene):
    """Return (ok, message). Cancel render when existing frames and not allowed."""
    props = scene.paai
    path, vdir, ver, is_new, info = build_output_path(props, locked_version=props.locked_version, do_claim=False)
    if not vdir:
        return True, ""
    if not cfg.version_has_frames(vdir):
        return True, ""
    settings = cfg.show_settings(props.root)
    confirm = settings.get("confirm_overwrite", not settings.get("allow_overwrite", False))
    if not confirm:
        return True, ""
    if getattr(props, "allow_overwrite", False):
        return True, ""
    return False, ("PAAI Pipeline: version %s already has frames. Enable 'Allow Overwrite' to continue." % ver)


def write_render_note(scene):
    props = scene.paai
    path, vdir, ver, is_new, info = build_output_path(props, locked_version=props.locked_version, do_claim=False)
    if not vdir:
        return
    bit_depth, compression = choices.fix_format(props.file_type, props.bit_depth, props.compression)
    fr = "%d-%d" % (scene.frame_start, scene.frame_end)
    cfg.write_note(
        vdir, props.note or "",
        source="blender",
        frames=fr,
        format=props.file_type or "",
        bit_depth=bit_depth,
        compression=compression,
        version=ver,
        sequence=props.sequence,
        shot=props.shot,
        type=props.render_type,
        name=props.name or "main",
    )
    try:
        props.locked_version = ""
    except Exception:
        pass
