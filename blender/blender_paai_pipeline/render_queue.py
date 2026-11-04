"""Blender: submit scenes / view layers to PAAI Render Queue."""
from __future__ import annotations
import os
import bpy
from bpy.props import (
    BoolProperty, IntProperty, FloatProperty, StringProperty,
    EnumProperty, CollectionProperty,
)
from bpy.types import Operator, Panel, PropertyGroup


def _link():
    """Stdlib queue client bundled with this add-on (no paai_render_queue import)."""
    from . import paai_queue_link as link
    return link


class PAAI_RQ_ViewLayerItem(PropertyGroup):
    name: StringProperty(name="View Layer")
    scene: StringProperty(name="Scene")
    selected: BoolProperty(name="", default=True)


class PAAI_RQ_Settings(PropertyGroup):
    frame_start: IntProperty(name="Start", default=1001)
    frame_end: IntProperty(name="End", default=1001)
    frame_step: IntProperty(name="Step", default=1, min=1)
    resolution_x: IntProperty(name="Res X", default=1920, min=1)
    resolution_y: IntProperty(name="Res Y", default=1080, min=1)
    resolution_percentage: IntProperty(name="Res %", default=100, min=1, max=100)
    fps: IntProperty(name="FPS", default=24, min=1)
    device: EnumProperty(
        name="Device",
        items=[("CPU", "CPU", ""), ("GPU", "GPU", "")],
        default="CPU",
    )
    cpu_cores: IntProperty(name="CPU threads", default=4, min=1)
    gpu_index: IntProperty(name="GPU index", default=0, min=0)
    priority: IntProperty(name="Priority", default=50, min=0, max=100)
    queue_url: StringProperty(name="Queue URL", default="")
    render_queue_path: StringProperty(
        name="Render Queue path",
        description="Optional folder (queue data / discovery) or URL; saved in show_config.txt",
        default="", subtype="DIR_PATH",
    )
    items: CollectionProperty(type=PAAI_RQ_ViewLayerItem)


def refresh_items(scene):
    props = scene.paai_rq
    props.items.clear()
    for sc in bpy.data.scenes:
        for vl in sc.view_layers:
            it = props.items.add()
            it.scene = sc.name
            it.name = vl.name
            it.selected = True


def sync_defaults_from_scene(scene):
    props = scene.paai_rq
    props.frame_start = scene.frame_start
    props.frame_end = scene.frame_end
    try:
        from . import pipeline_config as cfg
        root = getattr(getattr(scene, "paai", None), "root", "") or ""
        if root:
            sf = cfg.start_frame(root)
            if props.frame_start == 1 and props.frame_end == scene.frame_end == 1:
                props.frame_start = sf
                props.frame_end = sf
            if not props.render_queue_path:
                props.render_queue_path = cfg.render_queue_path(root) or ""
    except Exception:
        pass
    props.frame_step = scene.frame_step
    props.resolution_x = scene.render.resolution_x
    props.resolution_y = scene.render.resolution_y
    props.resolution_percentage = scene.render.resolution_percentage
    props.fps = scene.render.fps
    props.cpu_cores = max(1, scene.render.threads or 4)


class PAAI_OT_rq_refresh(Operator):
    bl_idname = "paai.rq_refresh"
    bl_label = "Refresh Scenes / View Layers"

    def execute(self, context):
        refresh_items(context.scene)
        sync_defaults_from_scene(context.scene)
        return {"FINISHED"}


class PAAI_OT_rq_open(Operator):
    bl_idname = "paai.rq_open"
    bl_label = "Open Render Queue"

    def execute(self, context):
        props = context.scene.paai_rq
        show_root = getattr(getattr(context.scene, "paai", None), "root", "") or ""
        qp = props.render_queue_path or ""
        link = _link()
        link.open_ui(base_url=props.queue_url or None, show_root=show_root, queue_path=qp)
        return {"FINISHED"}


class PAAI_OT_rq_submit(Operator):
    bl_idname = "paai.rq_submit"
    bl_label = "Submit to Render Queue"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.paai_rq
        show_root = ""
        try:
            show_root = (getattr(context.scene, "paai", None) and context.scene.paai.root) or ""
        except Exception:
            pass
        qp = props.render_queue_path or ""
        if show_root and qp:
            try:
                from . import pipeline_config as cfg
                cfg.set_show_setting(show_root, "render_queue_path", cfg.norm_path(qp))
            except Exception:
                pass
        link = _link()
        # save blend copy source
        blend = bpy.data.filepath
        if not blend:
            self.report({"ERROR"}, "PAAI Pipeline: Save the .blend file first")
            return {"CANCELLED"}
        bpy.ops.wm.save_mainfile()
        picked = [it for it in props.items if it.selected]
        if not picked:
            self.report({"ERROR"}, "PAAI Pipeline: Select at least one view layer")
            return {"CANCELLED"}
        jobs = []
        for it in picked:
            jobs.append({
                "app": "blender",
                "name": "%s · %s / %s" % (os.path.basename(blend), it.scene, it.name),
                "copy_from": blend,
                "target": "%s/%s" % (it.scene, it.name),
                "frames": {
                    "start": props.frame_start,
                    "end": props.frame_end,
                    "step": props.frame_step,
                },
                "resources": {
                    "cpu_cores": props.cpu_cores,
                    "gpu_index": props.gpu_index if props.device == "GPU" else None,
                },
                "priority": props.priority,
                "output_path": bpy.path.abspath(context.scene.render.filepath),
                "extra": {
                    "scene": it.scene,
                    "view_layer": it.name,
                    "resolution_x": props.resolution_x,
                    "resolution_y": props.resolution_y,
                    "resolution_percentage": props.resolution_percentage,
                    "fps": props.fps,
                    "device": props.device,
                    "show_root": show_root,
                },
            })
        res = link.submit(jobs, base_url=props.queue_url or None, show_root=show_root, queue_path=qp)
        if not res.get("ok"):
            self.report({"ERROR"}, res.get("message") or "PAAI Render Queue not running")
            return {"CANCELLED"}
        self.report({"INFO"}, "PAAI Pipeline: " + (res.get("message") or "submitted"))
        print("[PAAI Pipeline RQ]", res.get("message"), "jobs", len(res.get("jobs") or []))
        return {"FINISHED"}


class PAAI_PT_rq(Panel):
    bl_label = "Render Queue"
    bl_idname = "PAAI_PT_rq"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "output"
    bl_parent_id = "PAAI_PT_output"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.paai_rq
        row = layout.row(align=True)
        row.prop(props, "queue_url", text="Queue URL")
        row.operator("paai.rq_open", text="", icon="URL")
        row.operator("paai.rq_refresh", text="", icon="FILE_REFRESH")
        layout.prop(props, "render_queue_path")

        box = layout.box()
        box.label(text="Scenes / View Layers")
        if not props.items:
            box.operator("paai.rq_refresh", icon="FILE_REFRESH")
        for it in props.items:
            r = box.row(align=True)
            r.prop(it, "selected", text="")
            r.label(text="%s / %s" % (it.scene, it.name))

        col = layout.column(align=True)
        col.label(text="Overrides")
        row = col.row(align=True)
        row.prop(props, "frame_start")
        row.prop(props, "frame_end")
        row.prop(props, "frame_step")
        row = col.row(align=True)
        row.prop(props, "resolution_x")
        row.prop(props, "resolution_y")
        row.prop(props, "resolution_percentage")
        col.prop(props, "fps")
        row = col.row(align=True)
        row.prop(props, "device", expand=True)
        if props.device == "CPU":
            col.prop(props, "cpu_cores")
        else:
            col.prop(props, "gpu_index")
        col.prop(props, "priority")
        layout.operator("paai.rq_submit", icon="RENDER_ANIMATION")


classes = (
    PAAI_RQ_ViewLayerItem,
    PAAI_RQ_Settings,
    PAAI_OT_rq_refresh,
    PAAI_OT_rq_open,
    PAAI_OT_rq_submit,
    PAAI_PT_rq,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.paai_rq = bpy.props.PointerProperty(type=PAAI_RQ_Settings)


def unregister():
    del bpy.types.Scene.paai_rq
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
