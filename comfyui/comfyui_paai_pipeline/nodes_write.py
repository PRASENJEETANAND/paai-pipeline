"""PAAI Write node: save IMAGE batch into the shared show folder layout."""
import os
import numpy as np

from . import pipeline_config as cfg
from . import scan
from . import image_io
from . import choices

NEW = "New"


def _torch_to_np(images):
    if hasattr(images, "cpu"):
        arr = images.cpu().numpy()
    else:
        arr = np.asarray(images)
    return arr.astype(np.float32)


class PAAI_Write:
    @classmethod
    def INPUT_TYPES(cls):
        c = choices.initial()
        types = list(c["types"])
        show_default = (c.get("default_type") or cfg.default_type(cfg.start_root() or "", "comfyui") or "comfyui")
        if show_default in types:
            types = [show_default] + [x for x in types if x != show_default]
        elif "comfyui" in types:
            types = ["comfyui"] + [x for x in types if x != "comfyui"]
        start = int(c.get("start_frame") or cfg.START_FRAME_DEFAULT)
        return {
            "required": {
                "images": ("IMAGE",),
                "root": ("STRING", {"default": cfg.start_root() or "", "multiline": False}),
                "sequence": (c["sequences"],),
                "shot": (c["shots"],),
                "type": (types,),
                "name": ("STRING", {"default": cfg.DEFAULT_NAME, "multiline": False}),
                "version": (c.get("versions") or [NEW],),
                "claim": ("BOOLEAN", {"default": True}),
                "allow_overwrite": ("BOOLEAN", {"default": False}),
                "note": ("STRING", {"default": "", "multiline": True}),
                "file_type": (choices.FILE_TYPES,),
                "bit_depth": (choices.all_values("bit_depth"),),
                "compression": (choices.all_values("compression"),),
                "start_frame": ("INT", {"default": start, "min": 0, "max": 999999}),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("path",)
    FUNCTION = "write"
    OUTPUT_NODE = True
    CATEGORY = "PAAI Pipeline"

    def write(self, images, root, sequence, shot, type, name, version, note,
              file_type, bit_depth, compression, start_frame,
              claim=True, allow_overwrite=False):
        root = cfg.norm_path(root or "")
        if not root or not sequence or not shot:
            raise RuntimeError("PAAI Write: root, sequence and shot are required")
        cfg.ensure_config(root)
        name = (name or cfg.DEFAULT_NAME).strip().replace(" ", "_") or cfg.DEFAULT_NAME
        rtype = (type or cfg.default_type(root, "comfyui") or "comfyui").strip()
        parent = scan.type_dir(root, sequence, shot, rtype, name)
        is_new = (version or NEW) == NEW

        if claim:
            preferred = NEW if is_new else version
            ver, vdir, _ = cfg.claim_version(parent, preferred, source_app="comfyui")
        else:
            ver = scan.next_version(root, sequence, shot, rtype, name) if is_new else version
            if not cfg.is_version(ver):
                raise RuntimeError("PAAI Write: bad version %r" % ver)
            vdir = cfg.join_path(parent, ver)

        if cfg.version_has_frames(vdir):
            # confirm_overwrite is legacy alias; allow_overwrite show key is preferred
            settings = cfg.show_settings(root)
            confirm = settings.get("confirm_overwrite", not settings.get("allow_overwrite", False))
            if confirm and not allow_overwrite:
                raise RuntimeError(
                    "PAAI Write: version %s already has frames. "
                    "Enable allow_overwrite to replace them." % ver
                )

        bit_depth, compression = choices.fix_format(file_type, bit_depth, compression)
        ext = choices.ext_for(file_type)
        pattern = scan.build_path(root, sequence, shot, rtype, name, ver, ext)
        arr = _torch_to_np(images)
        if arr.ndim == 3:
            arr = arr[None, ...]
        n = arr.shape[0]
        default_start = cfg.start_frame(root)
        start = int(start_frame if start_frame is not None else default_start)
        written = []
        for i in range(n):
            frame_no = start + i
            if "####" in pattern:
                fpath = pattern.replace("####", "%04d" % frame_no)
            elif "#" in os.path.basename(pattern):
                base = os.path.basename(pattern)
                j = base.find("#"); k = j
                while k < len(base) and base[k] == "#":
                    k += 1
                pad = k - j
                fpath = os.path.join(os.path.dirname(pattern),
                                     base[:j] + ("%0*d" % (pad, frame_no)) + base[k:])
            else:
                fpath = pattern
                image_io.write_image_file(fpath, arr[i], file_type=ext,
                                          bit_depth=bit_depth, compression=compression)
                written.append(fpath)
                break
            image_io.write_image_file(fpath, arr[i], file_type=ext,
                                      bit_depth=bit_depth, compression=compression)
            written.append(fpath)

        vdir = os.path.dirname(written[0]) if written else vdir
        cfg.write_note(
            vdir, note or "",
            source="comfyui",
            frames="%d-%d" % (start, start + n - 1),
            format=file_type,
            bit_depth=bit_depth,
            compression=compression,
            count=n,
            version=ver,
            sequence=sequence,
            shot=shot,
            type=rtype,
            name=name,
        )
        try:
            cfg.add_name(root, rtype, name)
        except Exception:
            pass

        ui_text = pattern if "####" in pattern else (written[0] if written else pattern)
        return {"ui": {"text": [ui_text]}, "result": (ui_text,)}


NODES = {"PAAI_Write": PAAI_Write}
NAMES = {"PAAI_Write": "PAAI Write"}
