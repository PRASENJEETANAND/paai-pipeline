"""Read / write images for PAAI Load and Write. OpenEXR -> OIIO -> cv2 -> PIL fallbacks."""
import os
import numpy as np

ORDER = ["R", "G", "B", "A", "X", "Y", "Z", "U", "V", "W"]


def _split(name):
    if "." in name:
        layer, ch = name.rsplit(".", 1)
    else:
        layer, ch = (("depth", name) if name in ("Z", "ZBack")
                     else ("rgba", name) if name in ("R", "G", "B", "A")
                     else (name, name))
    return layer, ch


def _sort_ch(chs):
    return sorted(chs, key=lambda c: (ORDER.index(c.upper()) if c.upper() in ORDER else 99, c))


def list_exr_layers(path):
    """Return ordered layer names for a multi-layer EXR (or ['rgba'] for other formats)."""
    if not path or not os.path.isfile(path):
        return ["rgba"]
    if not path.lower().endswith(".exr"):
        return ["rgba"]
    try:
        layers = read_exr(path, header_only=True)
        names = list(layers.keys())
        # prefer rgba first
        names.sort(key=lambda n: (0 if n == "rgba" else 1, n))
        return names or ["rgba"]
    except Exception:
        return ["rgba"]


def _read_exr_legacy(path, header_only=False):
    import OpenEXR, Imath
    f = OpenEXR.InputFile(path)
    hdr = f.header()
    dw = hdr["dataWindow"]
    W, H = dw.max.x - dw.min.x + 1, dw.max.y - dw.min.y + 1
    chans = {}
    for cname in hdr["channels"]:
        if header_only:
            chans[cname] = None
        else:
            buf = f.channel(cname, Imath.PixelType(Imath.PixelType.FLOAT))
            chans[cname] = np.frombuffer(buf, dtype=np.float32).reshape(H, W)
    return chans


def read_exr(path, header_only=False):
    """{layer: {channel: np.float32[H,W]}} or {layer: [ch_names]} when header_only."""
    chans = {}
    try:
        import OpenEXR
        # Prefer legacy InputFile for reliable channel headers (OpenEXR.File
        # header_only often returns empty channel maps on single-part files).
        if header_only or not hasattr(OpenEXR, "File"):
            chans = _read_exr_legacy(path, header_only=header_only)
        else:
            try:
                with OpenEXR.File(path, separate_channels=True, header_only=False) as f:
                    parts = f.parts
                    for p in parts:
                        pname = p.name() if callable(getattr(p, "name", None)) else getattr(p, "name", "")
                        for cname, c in p.channels.items():
                            full = f"{pname}.{cname}" if (len(parts) > 1 and pname and "." not in cname) else cname
                            chans[full] = np.asarray(c.pixels, dtype=np.float32)
                if not chans:
                    chans = _read_exr_legacy(path, header_only=False)
            except Exception:
                chans = _read_exr_legacy(path, header_only=False)
    except ImportError:
        try:
            import OpenImageIO as oiio
            inp = oiio.ImageInput.open(path)
            if inp is None:
                raise IOError(oiio.geterror())
            spec = inp.spec()
            if header_only:
                for i, cname in enumerate(spec.channelnames):
                    chans[cname] = None
            else:
                pixels = inp.read_image(oiio.FLOAT)
                inp.close()
                arr = np.asarray(pixels, dtype=np.float32)
                if arr.ndim == 2:
                    chans[spec.channelnames[0] if spec.channelnames else "Y"] = arr
                else:
                    for i, cname in enumerate(spec.channelnames):
                        chans[cname] = arr[..., i]
            if not header_only and 'inp' in dir() and inp is not None:
                try:
                    inp.close()
                except Exception:
                    pass
        except ImportError:
            os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
            import cv2
            if header_only:
                return {"rgba": ["R", "G", "B", "A"]}
            im = cv2.imread(path, cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
            if im is None:
                raise IOError("cannot read %s (install OpenEXR)" % path)
            im = im.astype(np.float32)
            if im.ndim == 2:
                chans["Y"] = im
            else:
                names = ["B", "G", "R", "A"][:im.shape[2]]
                for i, n in enumerate(names):
                    chans[n] = im[..., i]
    layers = {}
    for full, arr in chans.items():
        layer, ch = _split(full)
        layers.setdefault(layer, {})[ch] = arr
    if header_only:
        return {l: _sort_ch(list(c.keys())) for l, c in layers.items()}
    return {l: {c: layers[l][c] for c in _sort_ch(list(layers[l].keys()))} for l in layers}


def read_image_file(path, layer="rgba"):
    """Any format -> float32 HxWxC (RGB or RGBA), values roughly display-linear / 0-1 for 8-bit."""
    path = path.replace("\\", "/")
    if path.lower().endswith(".exr"):
        layers = read_exr(path)
        if layer not in layers:
            # try case-insensitive / fallback
            for k in layers:
                if k.lower() == (layer or "").lower():
                    layer = k
                    break
            else:
                layer = "rgba" if "rgba" in layers else next(iter(layers))
        chmap = layers[layer]
        chs = _sort_ch(list(chmap.keys()))
        # prefer RGB(A)
        rgb = [c for c in ("R", "G", "B", "A") if c in chmap]
        if len(rgb) >= 3:
            stacks = [chmap[c] for c in rgb]
        else:
            stacks = [chmap[c] for c in chs[:4]]
            while len(stacks) < 3:
                stacks.append(stacks[-1])
        return np.stack(stacks, axis=-1).astype(np.float32)

    # movies
    ext = path.rsplit(".", 1)[-1].lower()
    if ext in ("mov", "mp4", "mxf", "avi"):
        return _read_movie_frame(path)

    from PIL import Image
    try:
        im = Image.open(path)
        mode = im.mode
        if mode in ("I;16", "I;16B", "I"):
            a = np.asarray(im, dtype=np.float32) / (65535.0 if "16" in mode else float(2 ** 31))
            return np.stack([a, a, a], axis=-1)
        if mode == "F":
            a = np.asarray(im, dtype=np.float32)
            return np.stack([a, a, a], axis=-1)
        im = im.convert("RGBA" if ("A" in mode or "transparency" in im.info) else "RGB")
        return np.asarray(im, dtype=np.float32) / 255.0
    except Exception:
        import cv2
        a = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if a is None:
            raise IOError("cannot read %s" % path)
        scale = 65535.0 if a.dtype == np.uint16 else 255.0 if a.dtype == np.uint8 else 1.0
        a = a.astype(np.float32) / scale
        if a.ndim == 2:
            return np.stack([a, a, a], axis=-1)
        # BGR(A) -> RGB(A)
        if a.shape[2] >= 4:
            return a[..., [2, 1, 0, 3]]
        return a[..., [2, 1, 0]]


def _read_movie_frame(path, index=0):
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            raise IOError("cannot read movie %s" % path)
        frame = frame.astype(np.float32) / 255.0
        return frame[..., ::-1].copy()  # BGR -> RGB
    except Exception:
        import imageio.v2 as imageio
        arr = imageio.imread(path)
        if arr.dtype == np.uint8:
            arr = arr.astype(np.float32) / 255.0
        else:
            arr = arr.astype(np.float32)
        return arr[..., :3] if arr.ndim == 3 else np.stack([arr, arr, arr], -1)


def write_image_file(path, rgb, file_type="png", bit_depth="8", compression="zip"):
    """Write HxWxC float image (0-1 or HDR) to path. Creates parent dirs."""
    path = path.replace("\\", "/")
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    arr = np.asarray(rgb, dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[..., None]
    ft = (file_type or "png").lower()
    if ft in ("jpeg",):
        ft = "jpg"
    if ft in ("tiff",):
        ft = "tif"

    if ft == "exr":
        return _write_exr(path, arr, bit_depth=bit_depth, compression=compression)

    return _write_raster(path, arr, ft, str(bit_depth), str(compression or ""))


def _num(text, default):
    digits = "".join(ch for ch in str(text) if ch.isdigit())
    return int(digits) if digits else default


def _png_level(compression):
    """Shared UI uses 'level 0..100'; map to zlib 0..9."""
    n = _num(compression, 15)
    if n > 9:
        return max(0, min(9, int(round(n * 9 / 100.0))))
    return max(0, min(9, n))


def _tiff_comp(compression):
    c = (compression or "lzw").lower().strip()
    return {"none": "none", "lzw": "lzw", "zip": "zip", "deflate": "zip",
            "packbits": "packbits"}.get(c, "lzw")


def _write_raster(path, arr, ft, bit_depth, compression):
    """png / jpg / tif with their own bit depth and compression options."""
    C = arr.shape[2]
    if C == 2:
        arr = arr[..., :1]
        C = 1
    keep_alpha = C >= 4 and ft in ("png", "tif")
    arr = arr[..., :4] if keep_alpha else (arr[..., :1] if C == 1 else arr[..., :3])
    if ft == "jpg":
        bit_depth = "8"
        if arr.shape[2] == 1:
            arr = np.repeat(arr, 3, axis=2)

    if bit_depth == "float" and ft == "tif":
        data = arr.astype(np.float32)
    elif bit_depth == "16" and ft in ("png", "tif"):
        data = (np.clip(arr, 0, 1) * 65535.0 + 0.5).astype(np.uint16)
    else:
        data = (np.clip(arr, 0, 1) * 255.0 + 0.5).astype(np.uint8)

    try:
        import cv2
        params = []
        if ft == "png":
            params = [cv2.IMWRITE_PNG_COMPRESSION, _png_level(compression)]
        elif ft == "jpg":
            params = [cv2.IMWRITE_JPEG_QUALITY, max(1, min(100, _num(compression, 95)))]
        elif ft == "tif":
            code = {"none": 1, "lzw": 5, "zip": 8, "deflate": 8, "packbits": 32773}.get(_tiff_comp(compression), 5)
            params = [cv2.IMWRITE_TIFF_COMPRESSION, code]
        img = data
        if img.shape[2] == 3:
            img = img[..., ::-1]
        elif img.shape[2] == 4:
            img = img[..., [2, 1, 0, 3]]
        else:
            img = img[..., 0]
        if not cv2.imwrite(path, np.ascontiguousarray(img), params):
            raise IOError("cv2 could not write " + path)
        return path
    except ImportError:
        pass

    # PIL fallback (8-bit everywhere, 16-bit greyscale only)
    from PIL import Image
    if data.dtype != np.uint8:
        if data.shape[2] == 1 and data.dtype == np.uint16:
            Image.fromarray(data[..., 0], mode="I;16").save(path)
            return path
        raise RuntimeError("PAAI Write: %s-bit %s needs opencv-python (pip install opencv-python)" % (bit_depth, ft))
    mode = {1: "L", 3: "RGB", 4: "RGBA"}[data.shape[2]]
    img = Image.fromarray(data[..., 0] if mode == "L" else data, mode)
    if ft == "png":
        img.save(path, compress_level=_png_level(compression))
    elif ft == "jpg":
        img.save(path, quality=max(1, min(100, _num(compression, 95))))
    else:
        comp = {"none": None, "lzw": "tiff_lzw", "zip": "tiff_adobe_deflate", "deflate": "tiff_adobe_deflate", "packbits": "packbits"}.get(_tiff_comp(compression), "tiff_lzw")
        img.save(path, compression=comp)
    return path


def _write_exr(path, arr, bit_depth="half", compression="zip"):
    H, W = arr.shape[:2]
    C = arr.shape[2]
    names = ["R", "G", "B", "A"][:C]
    import OpenEXR
    import Imath
    header = OpenEXR.Header(W, H)
    use_half = str(bit_depth).lower() in ("half", "16")
    pt = Imath.PixelType(Imath.PixelType.HALF if use_half else Imath.PixelType.FLOAT)
    header["channels"] = {n: Imath.Channel(pt) for n in names}
    # Compression: only set when the binding accepts Compression objects (skip on mismatch)
    try:
        Comp = getattr(Imath, "Compression", None) or getattr(OpenEXR, "Compression", None)
        if Comp is not None:
            cmap = {
                "zip": "ZIP_COMPRESSION", "zips": "ZIPS_COMPRESSION", "piz": "PIZ_COMPRESSION",
                "rle": "RLE_COMPRESSION", "pxr24": "PXR24_COMPRESSION", "none": "NO_COMPRESSION",
                "dwaa": "DWAA_COMPRESSION", "dwab": "DWAB_COMPRESSION",
            }
            key = cmap.get((compression or "zip").lower())
            if key and hasattr(Comp, key):
                val = getattr(Comp, key)
                # Some builds want Compression(enum), others the enum itself
                try:
                    header["compression"] = Comp(val) if not isinstance(val, Comp) else val
                except Exception:
                    try:
                        header["compression"] = val
                    except Exception:
                        pass
    except Exception:
        pass
    try:
        out = OpenEXR.OutputFile(path, header)
    except Exception:
        # retry without compression key
        header = OpenEXR.Header(W, H)
        header["channels"] = {n: Imath.Channel(pt) for n in names}
        out = OpenEXR.OutputFile(path, header)
    data = {}
    for i, n in enumerate(names):
        plane = np.ascontiguousarray(arr[..., i], dtype=np.float32)
        if use_half:
            data[n] = plane.astype(np.float16).tobytes()
        else:
            data[n] = plane.tobytes()
    out.writePixels(data)
    out.close()
    return path
