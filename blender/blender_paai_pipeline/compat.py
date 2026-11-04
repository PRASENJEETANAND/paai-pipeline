"""Blender version compatibility helpers (4.2 / 5.x)."""
import bpy


def eevee_engine_id():
    """Return the EEVEE render engine identifier for this Blender build.

    Blender 4.2–4.5: BLENDER_EEVEE_NEXT
    Blender 5.0+:    BLENDER_EEVEE
    """
    ver = bpy.app.version
    if ver >= (5, 0, 0):
        return "BLENDER_EEVEE"
    # 3.x used BLENDER_EEVEE; 4.2+ Next until 5.0 rename
    if ver >= (4, 2, 0):
        return "BLENDER_EEVEE_NEXT"
    return "BLENDER_EEVEE"


def available_engines():
    try:
        return [e.identifier for e in bpy.types.RenderEngine.__subclasses__()]  # may be empty
    except Exception:
        return []
