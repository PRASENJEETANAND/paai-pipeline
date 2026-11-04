"""comfyui_paai_pipeline: shared show Render Browser + PAAI Load / Write for ComfyUI.

Drop this folder into ComfyUI/custom_nodes and restart. Uses the same
<ROOT>/<SEQ>/<SHOT>/paai/... layout and showset/config as the Nuke tools.
"""
from .nodes_load import NODES as _L, NAMES as _LN
from .nodes_write import NODES as _W, NAMES as _WN

NODE_CLASS_MAPPINGS = {}
NODE_CLASS_MAPPINGS.update(_L)
NODE_CLASS_MAPPINGS.update(_W)
NODE_DISPLAY_NAME_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS.update(_LN)
NODE_DISPLAY_NAME_MAPPINGS.update(_WN)

WEB_DIRECTORY = "./web"

try:
    from .routes import setup_routes
    setup_routes()
except Exception as _e:  # pragma: no cover
    print("[PAAI Pipeline] routes not registered: %s" % _e)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
