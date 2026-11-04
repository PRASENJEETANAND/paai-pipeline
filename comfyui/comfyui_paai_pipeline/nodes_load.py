"""PAAI Load node: load a pipeline render as an IMAGE batch with AOV / cap / skip / nth."""
import os
import hashlib
import numpy as np

from . import pipeline_config as cfg
from . import scan
from . import image_io
from . import choices


def _torch():
    try:
        import torch
        return torch
    except ImportError:
        # Minimal stub so unit tests can run without torch installed.
        class _Tensor:
            def __init__(self, arr):
                self._a = np.asarray(arr, dtype=np.float32)
            @property
            def shape(self):
                return self._a.shape
            def cpu(self):
                return self
            def numpy(self):
                return self._a
            def __getitem__(self, i):
                return _Tensor(self._a[i])
        class _Torch:
            float32 = np.float32
            @staticmethod
            def from_numpy(a):
                return _Tensor(a)
            @staticmethod
            def zeros(shape, dtype=None, device=None):
                return _Tensor(np.zeros(shape, dtype=np.float32))
            class Tensor:
                pass
        _Torch.Tensor = _Tensor
        return _Torch()


def _to_image_mask(frames):
    """frames: list of HxWxC float -> IMAGE (B,H,W,3), MASK (B,H,W), w, h."""
    torch = _torch()
    if not frames:
        img = torch.zeros((1, 64, 64, 3))
        mask = torch.zeros((1, 64, 64))
        return img, mask, 0, 64, 64
    rgb, masks = [], []
    for f in frames:
        if f.ndim == 2:
            f = np.stack([f, f, f], -1)
        if f.shape[2] >= 4:
            masks.append(f[..., 3])
            rgb.append(f[..., :3])
        else:
            rgb.append(f[..., :3])
            masks.append(np.ones(f.shape[:2], dtype=np.float32))
    batch = np.stack(rgb, 0).astype(np.float32)
    mbatch = np.stack(masks, 0).astype(np.float32)
    H, W = batch.shape[1], batch.shape[2]
    return torch.from_numpy(batch), torch.from_numpy(mbatch), batch.shape[0], W, H


def _pick_files(pattern, skip_first=0, every_nth=1, cap=0):
    files = scan.resolve_frame_files(pattern)
    if not files:
        return []
    # skip / nth / cap (like Load Image Batch)
    skip_first = max(0, int(skip_first or 0))
    every_nth = max(1, int(every_nth or 1))
    files = files[skip_first:]
    files = files[::every_nth]
    if cap and int(cap) > 0:
        files = files[:int(cap)]
    return files


class PAAI_Load:
    @classmethod
    def INPUT_TYPES(cls):
        c = choices.initial(for_load=True)
        return {
            "required": {
                "root": ("STRING", {"default": cfg.start_root() or "", "multiline": False}),
                "sequence": (c["sequences"],),
                "shot": (c["shots"],),
                "type": (c["types"],),
                "name": (c["names"],),
                "version": (c["versions"] or [""],),
                "aov": (["rgba"],),
                "image_load_cap": ("INT", {"default": 0, "min": 0, "max": 100000}),
                "skip_first_frames": ("INT", {"default": 0, "min": 0, "max": 100000}),
                "select_every_nth": ("INT", {"default": 1, "min": 1, "max": 1000}),
            },
            "optional": {
                "path_override": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "INT", "INT", "INT")
    RETURN_NAMES = ("IMAGE", "MASK", "frame_count", "width", "height")
    FUNCTION = "load"
    CATEGORY = "PAAI Pipeline"

    @classmethod
    def VALIDATE_INPUTS(cls, sequence, shot, type, name, version, aov):
        # Lists change with the show on disk; the UI refreshes them, so skip ComfyUI's fixed-list check.
        return True

    @classmethod
    def IS_CHANGED(cls, root, sequence, shot, type, name, version, aov,
                   image_load_cap, skip_first_frames, select_every_nth, path_override=""):
        pattern = (path_override or "").strip()
        if not pattern and root and sequence and shot and type and version:
            pattern = scan.build_path(root, sequence, shot, type, name, version,
                                      cfg.type_ext(root, type))
        files = _pick_files(pattern, skip_first_frames, select_every_nth, image_load_cap)
        h = hashlib.sha1()
        h.update((pattern + "|" + (aov or "")).encode())
        for _, p in files[:50]:
            try:
                st = os.stat(p)
                h.update(("%s:%s:%s" % (p, st.st_mtime_ns, st.st_size)).encode())
            except Exception:
                h.update(p.encode())
        return h.hexdigest()

    def load(self, root, sequence, shot, type, name, version, aov,
             image_load_cap, skip_first_frames, select_every_nth, path_override=""):
        pattern = (path_override or "").strip()
        if not pattern:
            if not (root and sequence and shot and type and version):
                raise RuntimeError("PAAI Load: set root/sequence/shot/type/version or path_override")
            # find actual pattern from disk if version folder exists
            vdir = os.path.join(scan.type_dir(root, sequence, shot, type, name), version)
            seqs = scan.find_sequences(vdir)
            if seqs:
                pattern = seqs[0][0]
            else:
                pattern = scan.build_path(root, sequence, shot, type, name, version,
                                          cfg.type_ext(root, type))
        files = _pick_files(pattern, skip_first_frames, select_every_nth, image_load_cap)
        if not files:
            raise RuntimeError("PAAI Load: no frames found for %s" % pattern)
        frames = []
        for _, fp in files:
            frames.append(image_io.read_image_file(fp, layer=aov or "rgba"))
        return _to_image_mask(frames)


NODES = {"PAAI_Load": PAAI_Load}
NAMES = {"PAAI_Load": "PAAI Load"}
