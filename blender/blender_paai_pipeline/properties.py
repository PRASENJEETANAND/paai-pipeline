"""Scene PropertyGroup for the PAAI Pipeline Output panel.

Enum items are cached as module-level tuples so Blender does not GC the strings
(classic EnumProperty dynamic-items bug).
"""
import bpy
from bpy.props import (
    StringProperty, EnumProperty, BoolProperty, PointerProperty,
)
from bpy.types import PropertyGroup

from . import pipeline_config as cfg
from . import scan
from . import choices
from . import choices_blender  # app maps; FORMATS with blender_format available if needed
from . import apply as apply_mod

# ----- cached enum item lists (must stay alive) -----
_SEQ_ITEMS = [("", "(no sequence)", "")]
_SHOT_ITEMS = [("", "(no shot)", "")]
_TYPE_ITEMS = [("cg_render", "cg_render", "")]
_VER_ITEMS = [(choices.NEW, "New", "Create the next version")]
_BIT_ITEMS = [("half", "half", ""), ("float", "float", ""), ("8", "8", ""), ("16", "16", "")]
_COMP_ITEMS = [("zip", "zip", "")]
_FILE_ITEMS = [(k, k, "") for k in choices.FILE_TYPES]


def _root_default():
    return cfg.start_root() or ""


def _refresh_enums(props):
    """Rebuild cached item lists from disk for the current root/selection."""
    global _SEQ_ITEMS, _SHOT_ITEMS, _TYPE_ITEMS, _VER_ITEMS, _BIT_ITEMS, _COMP_ITEMS
    root = (props.root or "").strip()
    d = choices.dropdowns(root, props.sequence, props.shot, props.render_type, props.name)
    if not d:
        prefs_type = "cg_render"
        _SEQ_ITEMS = [("", "(set root)", "")]
        _SHOT_ITEMS = [("", "(set root)", "")]
        types = list(cfg.DEFAULT_TYPES)
        _TYPE_ITEMS = [(t[0], t[0], "") for t in types] or [("cg_render", "cg_render", "")]
        # put cg_render first
        _TYPE_ITEMS = sorted(_TYPE_ITEMS, key=lambda x: 0 if x[0] == "cg_render" else 1)
        _VER_ITEMS = [(choices.NEW, "New", "Create the next version")]
    else:
        _SEQ_ITEMS = [(s, s, "") for s in d["sequences"]] or [("", "(none)", "")]
        _SHOT_ITEMS = [(s, s, "") for s in d["shots"]] or [("", "(none)", "")]
        types = list(d["types"])
        if "cg_render" in types:
            types = ["cg_render"] + [t for t in types if t != "cg_render"]
        _TYPE_ITEMS = [(t, t, "") for t in types] or [("cg_render", "cg_render", "")]
        _VER_ITEMS = [(v, v, "") for v in d["versions"]] or [(choices.NEW, "New", "")]
    ft = props.file_type if props.file_type in choices.FORMATS else "exr"
    fmt = choices.FORMATS[ft]
    _BIT_ITEMS = [(b, b, "") for b in fmt["bit_depth"]]
    _COMP_ITEMS = [(c, c, "") for c in fmt["compression"]]


def _seq_items(self, context):
    return _SEQ_ITEMS


def _shot_items(self, context):
    return _SHOT_ITEMS


def _type_items(self, context):
    return _TYPE_ITEMS


def _ver_items(self, context):
    return _VER_ITEMS


def _bit_items(self, context):
    return _BIT_ITEMS


def _comp_items(self, context):
    return _COMP_ITEMS


def _file_items(self, context):
    return _FILE_ITEMS


_UPDATING = False


def _on_update(self, context):
    global _UPDATING
    if _UPDATING:
        return
    _UPDATING = True
    try:
        # normalize name
        if self.name and " " in self.name:
            self.name = self.name.replace(" ", "_")
        _refresh_enums(self)
        # clamp enums to valid values after refresh
        valid_seqs = {i[0] for i in _SEQ_ITEMS}
        if self.sequence not in valid_seqs and _SEQ_ITEMS[0][0]:
            self.sequence = _SEQ_ITEMS[0][0]
        valid_shots = {i[0] for i in _SHOT_ITEMS}
        if self.shot not in valid_shots and _SHOT_ITEMS[0][0]:
            self.shot = _SHOT_ITEMS[0][0]
        valid_types = {i[0] for i in _TYPE_ITEMS}
        if self.render_type not in valid_types and _TYPE_ITEMS[0][0]:
            self.render_type = _TYPE_ITEMS[0][0]
        valid_vers = {i[0] for i in _VER_ITEMS}
        if self.version not in valid_vers:
            self.version = choices.NEW
        bd, co = choices.fix_format(self.file_type, self.bit_depth, self.compression)
        if self.bit_depth != bd:
            self.bit_depth = bd
        if self.compression != co:
            self.compression = co
        if context and context.scene:
            apply_mod.apply_to_scene(context.scene, create_dirs=False)
    finally:
        _UPDATING = False


def _on_root(self, context):
    _on_update(self, context)


class PAAI_SceneSettings(PropertyGroup):
    root: StringProperty(
        name="Root",
        description="Show / project root (contains showset/config)",
        default="",
        subtype="DIR_PATH",
        update=_on_root,
    )
    sequence: EnumProperty(name="Sequence", items=_seq_items, update=_on_update)
    shot: EnumProperty(name="Shot", items=_shot_items, update=_on_update)
    render_type: EnumProperty(name="Type", items=_type_items, update=_on_update)
    name: StringProperty(
        name="Name",
        description="Render name (spaces become underscores)",
        default=cfg.DEFAULT_NAME,
        update=_on_update,
    )
    version: EnumProperty(name="Version", items=_ver_items, update=_on_update)
    claim: BoolProperty(
        name="Claim",
        description="Atomically reserve the version folder (.claim). If taken, bump to next free",
        default=True,
    )
    allow_overwrite: BoolProperty(
        name="Allow Overwrite",
        description="Allow writing into a version that already has frames",
        default=False,
    )
    render_queue_path: StringProperty(
        name="Render Queue path",
        description="Optional queue data folder or URL (saved in show_config.txt)",
        default="",
        subtype="DIR_PATH",
    )
    note: StringProperty(name="Note", description="Saved into version_note.json on render", default="")
    file_type: EnumProperty(name="File Type", items=_file_items, update=_on_update)
    bit_depth: EnumProperty(name="Bit Depth", items=_bit_items, update=_on_update)
    compression: EnumProperty(name="Compression", items=_comp_items, update=_on_update)
    path_preview: StringProperty(name="Path", default="")
    path_info: StringProperty(name="Info", default="")
    locked_version: StringProperty(
        name="Locked Version",
        description="Internal: version folder locked for the current render session",
        default="",
        options={"HIDDEN"},
    )
    enabled: BoolProperty(
        name="Use PAAI Path",
        description="When on, F12 / cmdline renders write into the pipeline folder layout",
        default=True,
        update=_on_update,
    )


def init_scene_defaults(scene):
    """Fill empty props from prefs / disk once."""
    props = scene.paai
    prefs = cfg.load_prefs()
    # Migrate renamed claim_version -> claim on older scenes (RNA may still expose old attr briefly).
    if hasattr(props, "claim") and hasattr(props, "claim_version"):
        try:
            props.claim = bool(props.claim_version)
        except Exception:
            pass
    if not props.root:
        props.root = cfg.start_root() or prefs.get("root") or ""
    if not props.sequence:
        seq = cfg.prefs_sequence(prefs)
        if seq:
            # set after enums refresh below
            pass
    if props.root and not props.render_queue_path:
        try:
            props.render_queue_path = cfg.render_queue_path(props.root) or ""
        except Exception:
            pass
    if props.root:
        _refresh_enums(props)
        pref_seq = cfg.prefs_sequence(prefs)
        pref_shot = prefs.get("shot") or ""
        seq0 = props.sequence or pref_seq
        shot0 = props.shot or pref_shot
        app_fallback = "cg_render"
        show_def = cfg.default_type(props.root, app_fallback) or app_fallback
        d = choices.dropdowns(props.root, seq0, shot0,
                              props.render_type or show_def, props.name)
        if d:
            if not props.sequence and (d["sequence"] or pref_seq):
                props.sequence = d["sequence"] or pref_seq
            if not props.shot and (d["shot"] or pref_shot):
                props.shot = d["shot"] or pref_shot
            if not props.render_type or props.render_type in ("",):
                if show_def in d["types"]:
                    props.render_type = show_def
                elif "cg_render" in d["types"]:
                    props.render_type = "cg_render"
                elif d.get("type"):
                    props.render_type = d["type"]
            if not props.name:
                props.name = cfg.DEFAULT_NAME
            if not props.version:
                props.version = choices.NEW
        apply_mod.apply_to_scene(scene, create_dirs=False)


classes = (PAAI_SceneSettings,)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.paai = PointerProperty(type=PAAI_SceneSettings)


def unregister():
    del bpy.types.Scene.paai
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
