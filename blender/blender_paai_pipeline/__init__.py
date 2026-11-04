bl_info = {
    "name": "PAAI Pipeline",
    "author": "PAAI",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "Top bar > PAAI Pipeline | Properties > Output > PAAI Pipeline",
    "description": "Shared show render browser and output path panel (Nuke / ComfyUI compatible)",
    "category": "Render",
}

# Support both:
#   1) installed as a package folder blender_paai_pipeline/
#   2) reloaded via importlib
import importlib

from . import pipeline_config
from . import scan
from . import choices
from . import apply
from . import properties
from . import panel
from . import handlers
from . import ops
from . import browser
from . import render_queue


def register():
    properties.register()
    ops.register()
    panel.register()
    handlers.register()
    render_queue.register()
    # bpy.data is restricted during register — seed via timer / load_post
    try:
        import bpy
        def _seed():
            try:
                for scene in bpy.data.scenes:
                    properties.init_scene_defaults(scene)
            except Exception as e:
                print("[PAAI] init defaults:", e)
            return None
        if not bpy.app.background:
            bpy.app.timers.register(_seed, first_interval=0.1)
        else:
            # background: data is available after register returns; try immediate + timer
            bpy.app.timers.register(_seed, first_interval=0.0)
    except Exception as e:
        print("[PAAI] seed setup:", e)
    print("[PAAI Pipeline] add-on registered")


def unregister():
    render_queue.unregister()
    handlers.unregister()
    panel.unregister()
    ops.unregister()
    properties.unregister()
    try:
        from . import browser_web
        browser_web.stop()
    except Exception:
        pass
    print("[PAAI Pipeline] add-on unregistered")


if __name__ == "__main__":
    register()
