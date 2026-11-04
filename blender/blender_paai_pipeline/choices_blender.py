"""Blender-specific format mappings on top of shared choices.py."""
from .choices import (  # noqa: F401
    NEW, FORMATS as _SHARED_FORMATS, FILE_TYPES, all_values, fix_format,
    ext_for, png_zlib_level, dropdowns, initial, _pick,
)

# Extend FORMATS with Blender image_settings.file_format names (shared lists unchanged).
FORMATS = {
    k: dict(v, **extra) for k, v, extra in (
        ("exr", _SHARED_FORMATS["exr"], {"blender_format": "OPEN_EXR"}),
        ("exr multilayer", _SHARED_FORMATS["exr multilayer"], {"blender_format": "OPEN_EXR_MULTILAYER"}),
        ("png", _SHARED_FORMATS["png"], {"blender_format": "PNG"}),
        ("jpg", _SHARED_FORMATS["jpg"], {"blender_format": "JPEG"}),
        ("tiff", _SHARED_FORMATS["tiff"], {"blender_format": "TIFF"}),
    )
}
FILE_TYPES = list(FORMATS)

EXR_CODEC = {
    "none": "NONE", "zip": "ZIP", "zips": "ZIPS", "piz": "PIZ",
    "pxr24": "PXR24", "rle": "RLE", "dwaa": "DWAA", "dwab": "DWAB",
}
TIFF_CODEC = {
    "none": "NONE", "deflate": "DEFLATE", "zip": "DEFLATE",
    "lzw": "LZW", "packbits": "PACKBITS",
}
BIT_TO_DEPTH = {
    "8": "8", "16": "16", "half": "16", "float": "32",
}
