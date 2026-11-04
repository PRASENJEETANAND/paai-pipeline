"""PAAI Pipeline panel in Properties > Output."""
import bpy
from bpy.types import Panel

from . import apply as apply_mod
from . import choices


class PAAI_PT_output(Panel):
    bl_label = "PAAI Pipeline"
    bl_idname = "PAAI_PT_output"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "output"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(context.scene.paai, "enabled", text="")

    def draw(self, context):
        layout = self.layout
        props = context.scene.paai
        layout.active = props.enabled

        row = layout.row(align=True)
        row.prop(props, "root")
        row.operator("paai.refresh_enums", text="", icon="FILE_REFRESH")

        col = layout.column(align=True)
        col.prop(props, "sequence")
        r = col.row(align=True)
        r.prop(props, "shot")
        r.operator("paai.add_shot", text="", icon="ADD")
        r = col.row(align=True)
        r.prop(props, "render_type")
        r.operator("paai.add_type", text="", icon="ADD")
        col.prop(props, "name")
        row = col.row(align=True)
        row.prop(props, "version")
        row.prop(props, "claim", text="Claim")
        col.prop(props, "allow_overwrite")
        col.prop(props, "note")
        col.prop(props, "render_queue_path")

        box = layout.box()
        box.label(text="Format", icon="IMAGE_DATA")
        box.prop(props, "file_type")
        row = box.row(align=True)
        row.prop(props, "bit_depth")
        row.prop(props, "compression")

        box = layout.box()
        info = props.path_info or ""
        icon = "ERROR" if info.startswith("OVERWRITE") else "INFO"
        box.label(text=info or "(set root / sequence / shot)", icon=icon)
        path = props.path_preview or ""
        if path:
            # show truncated from the right (filename visible)
            box.label(text=path if len(path) < 72 else "…" + path[-70:], icon="FILE_FOLDER")
        row = box.row(align=True)
        row.operator("paai.apply_output", icon="CHECKMARK")
        row.operator("paai.open_output_folder", icon="FILE_FOLDER")


classes = (PAAI_PT_output,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
