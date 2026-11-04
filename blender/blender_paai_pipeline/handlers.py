"""Render handlers: claim/lock version, overwrite guard, expand frame, write note."""
import bpy
from bpy.app.handlers import persistent

from . import apply as apply_mod
from . import pipeline_config as cfg


@persistent
def paai_render_init(scene, depsgraph=None):
    try:
        if not getattr(scene, "paai", None) or not scene.paai.enabled:
            return
        props = scene.paai
        # Claim (or resolve) version for this whole render session
        path, vdir, ver, is_new, info = apply_mod.build_output_path(
            props, do_claim=bool(getattr(props, "claim", getattr(props, "claim_version", True))))
        props.locked_version = ver or ""
        ok, msg = apply_mod.check_overwrite_allowed(scene)
        if not ok:
            props.locked_version = ""
            # Cancel by raising — Blender aborts the render
            raise RuntimeError(msg)
        apply_mod.apply_to_scene(scene, create_dirs=True, expand_current_frame=True, do_claim=False)
        # Align scene frame start to show default when still at Blender default 1 and show says 1001
        try:
            sf = cfg.start_frame(props.root)
            if scene.frame_start == 1 and sf != 1 and scene.frame_end == 1:
                scene.frame_start = sf
                scene.frame_end = sf
                scene.frame_current = sf
        except Exception:
            pass
        print("[PAAI] render_init ->", scene.render.filepath, "ver", ver)
    except Exception as e:
        print("[PAAI] render_init:", e)
        raise


@persistent
def paai_render_pre(scene, depsgraph=None):
    try:
        if not getattr(scene, "paai", None) or not scene.paai.enabled:
            return
        ok, msg = apply_mod.check_overwrite_allowed(scene)
        if not ok:
            raise RuntimeError(msg)
        apply_mod.apply_to_scene(scene, create_dirs=True, expand_current_frame=True, do_claim=False)
    except Exception as e:
        print("[PAAI] render_pre:", e)
        raise


@persistent
def paai_render_complete(scene, depsgraph=None):
    try:
        if not getattr(scene, "paai", None) or not scene.paai.enabled:
            return
        apply_mod.write_render_note(scene)
        print("[PAAI] wrote version note for", scene.paai.path_preview)
    except Exception as e:
        print("[PAAI] render_complete:", e)


@persistent
def paai_render_cancel(scene, depsgraph=None):
    try:
        if getattr(scene, "paai", None):
            scene.paai.locked_version = ""
    except Exception:
        pass


@persistent
def paai_load_post(dummy=None):
    try:
        for scene in bpy.data.scenes:
            from . import properties
            properties.init_scene_defaults(scene)
    except Exception as e:
        print("[PAAI] load_post:", e)


def register():
    handlers = bpy.app.handlers
    for hlist, fn in (
        (handlers.render_init, paai_render_init),
        (handlers.render_pre, paai_render_pre),
        (handlers.render_complete, paai_render_complete),
        (handlers.render_cancel, paai_render_cancel),
        (handlers.load_post, paai_load_post),
    ):
        if fn not in hlist:
            hlist.append(fn)


def unregister():
    handlers = bpy.app.handlers
    for hlist, fn in (
        (handlers.render_init, paai_render_init),
        (handlers.render_pre, paai_render_pre),
        (handlers.render_complete, paai_render_complete),
        (handlers.render_cancel, paai_render_cancel),
        (handlers.load_post, paai_load_post),
    ):
        if fn in hlist:
            hlist.remove(fn)
