"""Operators: refresh, apply, add shot/type, open folder, load image, set as output, browser."""
import os
import bpy
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator

from . import pipeline_config as cfg
from . import scan
from . import choices
from . import apply as apply_mod
from . import properties


class PAAI_OT_refresh_enums(Operator):
    bl_idname = "paai.refresh_enums"
    bl_label = "Refresh"
    bl_description = "Rescan show config and versions"

    def execute(self, context):
        properties._refresh_enums(context.scene.paai)
        apply_mod.apply_to_scene(context.scene, create_dirs=False)
        self.report({"INFO"}, "PAAI Pipeline refreshed")
        return {"FINISHED"}


class PAAI_OT_apply_output(Operator):
    bl_idname = "paai.apply_output"
    bl_label = "Apply to Output"
    bl_description = "Set Blender output path and image format from the panel"

    def execute(self, context):
        path = apply_mod.apply_to_scene(context.scene, create_dirs=True)
        if not path:
            self.report({"ERROR"}, "PAAI Pipeline: Set root, sequence and shot first")
            return {"CANCELLED"}
        self.report({"INFO"}, "PAAI Pipeline: Output -> %s" % path)
        return {"FINISHED"}


class PAAI_OT_open_output_folder(Operator):
    bl_idname = "paai.open_output_folder"
    bl_label = "Open Folder"
    bl_description = "Open the version folder (creates it if needed)"

    def execute(self, context):
        path, vdir, ver, is_new, info = apply_mod.build_output_path(context.scene.paai)
        if not vdir:
            self.report({"ERROR"}, "PAAI Pipeline: Nothing to open yet")
            return {"CANCELLED"}
        os.makedirs(vdir, exist_ok=True)
        bpy.ops.wm.path_open(filepath=vdir)
        return {"FINISHED"}


class PAAI_OT_add_shot(Operator):
    bl_idname = "paai.add_shot"
    bl_label = "Add Shot"
    bl_description = "Add a shot to showset/config/shots.txt"
    bl_options = {"REGISTER", "UNDO"}

    sequence: StringProperty(name="Sequence", default="")
    shot: StringProperty(name="Shot", default="")
    make_folders: BoolProperty(name="Create folders", default=True)

    def invoke(self, context, event):
        props = context.scene.paai
        self.sequence = props.sequence or ""
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "sequence")
        layout.prop(self, "shot")
        layout.prop(self, "make_folders")

    def execute(self, context):
        root = context.scene.paai.root
        if not root or not self.sequence or not self.shot:
            self.report({"ERROR"}, "PAAI Pipeline: root, sequence and shot required")
            return {"CANCELLED"}
        cfg.add_shot(root, self.sequence, self.shot, make_folders=self.make_folders)
        props = context.scene.paai
        properties._refresh_enums(props)
        props.sequence = self.sequence.strip().replace(" ", "_")
        props.shot = self.shot.strip().replace(" ", "_")
        apply_mod.apply_to_scene(context.scene)
        self.report({"INFO"}, "PAAI Pipeline: Added %s/%s" % (self.sequence, self.shot))
        return {"FINISHED"}


class PAAI_OT_add_type(Operator):
    bl_idname = "paai.add_type"
    bl_label = "Add Type"
    bl_description = "Add a render type to showset/config/types.txt"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty(name="Type", default="")
    ext: StringProperty(name="Extension", default="exr")
    named: BoolProperty(name="Needs element name", default=False)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "name")
        layout.prop(self, "ext")
        layout.prop(self, "named")

    def execute(self, context):
        root = context.scene.paai.root
        n = self.name.strip().replace(" ", "_")
        if not root or not n:
            self.report({"ERROR"}, "PAAI Pipeline: root and type name required")
            return {"CANCELLED"}
        if not cfg.add_type(root, n, self.ext, self.named):
            self.report({"ERROR"}, "PAAI Pipeline: Type empty or already exists")
            return {"CANCELLED"}
        cfg.add_name(root, n, "main")
        props = context.scene.paai
        properties._refresh_enums(props)
        props.render_type = n
        apply_mod.apply_to_scene(context.scene)
        self.report({"INFO"}, "PAAI Pipeline: Added type %s" % n)
        return {"FINISHED"}


class PAAI_OT_set_as_output(Operator):
    """Fill the Output panel from a render dict (used by Render Browser)."""
    bl_idname = "paai.set_as_output"
    bl_label = "Set as Output"
    bl_options = {"REGISTER", "UNDO"}

    root: StringProperty()
    sequence: StringProperty()
    shot: StringProperty()
    render_type: StringProperty()
    name: StringProperty(default="main")
    version: StringProperty(default="New")

    def execute(self, context):
        props = context.scene.paai
        if self.root:
            props.root = self.root
        properties._refresh_enums(props)
        if self.sequence:
            props.sequence = self.sequence
        properties._refresh_enums(props)
        if self.shot:
            props.shot = self.shot
        if self.render_type:
            props.render_type = self.render_type
        if self.name:
            props.name = self.name
        properties._refresh_enums(props)
        # keep New if that was requested; else pick existing version
        if self.version and self.version != choices.NEW:
            props.version = self.version
        else:
            props.version = choices.NEW
        apply_mod.apply_to_scene(context.scene, create_dirs=False)
        self.report({"INFO"}, "PAAI Pipeline: Output set to %s/%s %s" % (self.sequence, self.shot, self.version))
        return {"FINISHED"}


class PAAI_OT_load_as_image(Operator):
    """Load a sequence into bpy.data.images as an IMAGE_SEQUENCE source."""
    bl_idname = "paai.load_as_image"
    bl_label = "Load as Image"
    bl_options = {"REGISTER", "UNDO"}

    path: StringProperty(description="File pattern with #### or a single file")
    name: StringProperty(default="")
    first: bpy.props.IntProperty(default=1)
    last: bpy.props.IntProperty(default=1)

    def execute(self, context):
        pattern = (self.path or "").replace("\\", "/")
        if not pattern:
            self.report({"ERROR"}, "PAAI Pipeline: No path")
            return {"CANCELLED"}
        files = scan.resolve_frame_files(pattern)
        if not files:
            # try as single file
            if os.path.isfile(pattern):
                files = [(None, pattern)]
            else:
                self.report({"ERROR"}, "PAAI Pipeline: No frames found at %s" % pattern)
                return {"CANCELLED"}
        first_path = files[0][1]
        img_name = self.name or os.path.basename(first_path)
        # strip frame digits for a clean name
        img = bpy.data.images.load(first_path, check_existing=True)
        img.name = img_name[:60]
        if len(files) > 1 and files[0][0] is not None:
            try:
                img.source = "SEQUENCE"
            except Exception:
                pass
            # Blender uses the filepath with # padding relative to the loaded file
            # Set frame range on the image user via the Image Editor if available
            try:
                img.filepath = pattern if "#" in pattern else first_path
            except Exception:
                pass
        # Also drop a Compositor Image node if compositor is active
        try:
            scene = context.scene
            scene.use_nodes = True
            tree = scene.node_tree
            node = tree.nodes.new("CompositorNodeImage")
            node.image = img
            node.label = img_name
            if len(files) > 1 and files[0][0] is not None:
                node.frame_duration = (self.last - self.first + 1) if self.last >= self.first else len(files)
                node.frame_start = self.first or files[0][0]
                node.frame_offset = 0
        except Exception as e:
            print("[PAAI] compositor node:", e)
        self.report({"INFO"}, "PAAI Pipeline: Loaded %s (%d frames)" % (img.name, len(files)))
        return {"FINISHED"}


class PAAI_OT_open_render_browser(Operator):
    bl_idname = "paai.open_render_browser"
    bl_label = "Render Browser"
    bl_description = "Open the PAAI Render Browser"

    def execute(self, context):
        from . import browser
        browser.show(context)
        return {"FINISHED"}




class PAAI_OT_show_create_check(Operator):
    bl_idname = "paai.show_create_check"
    bl_label = "Create / Check Show"
    bl_description = "Create showset/config and shot folders, then validate the show tree"
    bl_options = {"REGISTER"}

    root: StringProperty(name="Show root", subtype="DIR_PATH", default="")
    sequence: StringProperty(name="Sequence", default="SQ010")
    shots: StringProperty(name="Shots", description="Comma-separated", default="SH010")

    def invoke(self, context, event):
        try:
            from . import pipeline_config as cfg
            if not self.root:
                self.root = (getattr(context.scene.paai, "root", None) or cfg.start_root() or "")
        except Exception:
            pass
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "root")
        layout.prop(self, "sequence")
        layout.prop(self, "shots")

    def execute(self, context):
        from . import paai_show
        root = (self.root or "").strip()
        pairs = paai_show._parse_shots_arg(self.sequence, self.shots)
        if not root:
            self.report({"ERROR"}, "PAAI Pipeline: show root required")
            return {"CANCELLED"}
        if not pairs:
            # check-only when no shots typed
            code, lines = paai_show.check_show(root, quiet=True)
            for line in lines[:12]:
                print("[PAAI Show]", line)
            level = {"INFO"} if code == 0 else ({"WARNING"} if code == 1 else {"ERROR"})
            self.report(level, "PAAI Pipeline: " + lines[0])
            return {"FINISHED"} if code < 2 else {"CANCELLED"}
        paai_show.create_show(root, pairs, quiet=True)
        code, lines = paai_show.check_show(root, quiet=True)
        for line in lines[:20]:
            print("[PAAI Show]", line)
        try:
            from . import pipeline_config as cfg
            cfg.save_prefs(root=cfg.norm_path(root))
            if hasattr(context.scene, "paai"):
                context.scene.paai.root = cfg.norm_path(root)
        except Exception:
            pass
        level = {"INFO"} if code == 0 else ({"WARNING"} if code == 1 else {"ERROR"})
        self.report(level, "PAAI Pipeline: " + lines[0])
        return {"FINISHED"} if code < 2 else {"CANCELLED"}

class PAAI_MT_pipeline(bpy.types.Menu):
    bl_label = "PAAI Pipeline"
    bl_idname = "PAAI_MT_pipeline"

    def draw(self, context):
        layout = self.layout
        layout.operator("paai.open_render_browser", icon="FILE_FOLDER")
        layout.operator("paai.show_create_check", icon="NEWFOLDER")
        layout.operator("paai.rq_submit", icon="RENDER_ANIMATION")
        layout.operator("paai.rq_open", icon="URL")


def _draw_pipeline_menu(self, context):
    self.layout.menu("PAAI_MT_pipeline")


classes = (
    PAAI_OT_refresh_enums,
    PAAI_OT_apply_output,
    PAAI_OT_open_output_folder,
    PAAI_OT_add_shot,
    PAAI_OT_add_type,
    PAAI_OT_set_as_output,
    PAAI_OT_load_as_image,
    PAAI_OT_open_render_browser,
    PAAI_OT_show_create_check,
    PAAI_MT_pipeline,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.TOPBAR_MT_editor_menus.append(_draw_pipeline_menu)


def unregister():
    bpy.types.TOPBAR_MT_editor_menus.remove(_draw_pipeline_menu)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
