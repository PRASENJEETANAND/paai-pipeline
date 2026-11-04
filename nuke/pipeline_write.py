"""Pipeline Write node.

Sequence / Shot / Render type dropdowns are built from your folders.
Version dropdown: "New" creates the next version on every render;
picking an existing version (v003 ...) overwrites it.

Path: <ROOT>/<SEQ>/<SHOT>/paai/<type>/[<name>/]v###/<SEQ>_<SHOT>_<type>[_<name>]_v###.####.<ext>
"""
import os
import re
import nuke
import pipeline_config as cfg

TAB = "PAAI Pipeline"
NONE = "-- none --"
NEW = "New"


def _root(node):
    return cfg.norm_path(node["pl_root"].value() or "")


def _set_menu(knob, values, fallback=None):
    current = knob.value()
    values = values or [NONE]
    knob.setValues(values)
    knob.setValue(current if current in values else (fallback or values[0]))


MOVIE_EXTS = {"mov", "mp4", "mxf", "avi"}


def _elem_name(node):
    """Every render has a name folder under its type: <type>/<name>/v###.
    Empty Name = 'main'."""
    return node["pl_name"].value().strip().replace(" ", "_") or cfg.DEFAULT_NAME


def _ext(node):
    """Extension follows the Write's file type (falls back to the type's default)."""
    try:
        ft = node["file_type"].value()
    except Exception:
        ft = ""
    ext = (ft or cfg.type_ext(_root(node), node["pl_type"].value())).lower()
    return {"jpeg": "jpg", "tiff": "tif", "ffmpeg": "mov", "mov64": "mov"}.get(ext, ext)


def set_type_filetype(node):
    """Switching render type sets the file type to that type's default from types.txt."""
    try:
        node["file_type"].setValue(cfg.type_ext(_root(node), node["pl_type"].value()))
    except Exception:
        pass


def _type_dir(node):
    rtype = node["pl_type"].value()
    return cfg.join_path(_root(node), node["pl_sequence"].value(), node["pl_shot"].value(),
                         cfg.render_subdir(_root(node)), rtype, _elem_name(node))


def _existing_versions(node):
    """Existing v### folders, newest first."""
    return sorted((d for d in cfg.list_dirs(_type_dir(node)) if cfg.is_version(d)),
                  key=lambda d: int(d[1:]), reverse=True)


def _next_version(node):
    vers = _existing_versions(node)
    return "v%03d" % (int(vers[0][1:]) + 1 if vers else 1)


def refresh_sequences(node):
    if os.path.isdir(_root(node)):
        cfg.ensure_config(_root(node))
    _set_menu(node["pl_sequence"], list(cfg.list_shots(_root(node))))
    refresh_types(node)
    refresh_shots(node)


def refresh_types(node):
    _set_menu(node["pl_type"], cfg.render_types(_root(node)))


def refresh_shots(node):
    _set_menu(node["pl_shot"], cfg.list_shots(_root(node)).get(node["pl_sequence"].value(), []))
    update_path(node)


def refresh_versions(node):
    _set_menu(node["pl_version"], [NEW] + _existing_versions(node), fallback=NEW)


def update_path(node, rescan_versions=True):
    if "pl_custom" in node.knobs() and node["pl_custom"].value():
        return   # Write had a non-pipeline path: leave it alone until you pick a seq/shot/type
    seq, shot, rtype = node["pl_sequence"].value(), node["pl_shot"].value(), node["pl_type"].value()
    if NONE in (seq, shot):
        node["file"].setValue("")
        node["pl_info"].setValue("<font color=orange>Pick a valid sequence and shot</font>")
        return
    if rescan_versions:
        refresh_versions(node)
    is_new = node["pl_version"].value() == NEW
    ver = _next_version(node) if is_new else node["pl_version"].value()
    ext = _ext(node)
    tag = "%s_%s" % (rtype, _elem_name(node))
    frames = "" if ext in MOVIE_EXTS else ".####"
    fname = "%s_%s_%s_%s%s.%s" % (seq, shot, tag, ver, frames, ext)
    node["file"].setValue("%s/%s/%s" % (_type_dir(node), ver, fname))
    if is_new:
        msg = "<font color=lightgreen>NEW version  %s | %s | %s | %s</font>"
    else:
        msg = "<font color=orange>OVERWRITE  %s | %s | %s | %s</font>"
    node["pl_info"].setValue(msg % (seq, shot, tag, ver))
    node["label"].setValue("%s_%s\n%s %s" % (seq, shot, tag, "NEW " + ver if is_new else ver))


# ------------------------------------------------------------------ main-panel settings on Pipeline tab
COMMON_KNOBS = ["file", "channels", "file_type", "colorspace", "raw", "views",
                "premultiplied", "create_directories"]
# format-specific knobs: only the ones that exist for the current file type get shown
FORMAT_KNOBS = ["datatype", "compression", "dw_compression_level", "metadata", "noprefix",
                "interleave", "autocrop", "write_full_layer", "heroview", "standard_layer_name_format",
                "_jpeg_quality", "_jpeg_sub_sampling", "transfer", "bigEndian", "fill",
                "mov64_codec", "mov_prores_codec_profile", "mov_h264_codec_profile", "mov64_fps",
                "mov64_bitrate", "mov64_quality_min", "mov64_quality_max", "mov64_audiofile"]
RANGE_KNOBS = ["use_limit", "first", "last", "Render"]
LINK_PREFIX = "pl_lnk_"


def build_output_links(node, force=False):
    """Mirror the Write tab's output settings (file type, data type, compression...) on the
    Pipeline tab. Rebuilt when the file type changes, since each format has different knobs."""
    knobs = node.knobs()
    wanted = [n for n in COMMON_KNOBS + FORMAT_KNOBS + RANGE_KNOBS if n in knobs]
    have = [k[len(LINK_PREFIX):] for k in knobs if k.startswith(LINK_PREFIX)]
    if sorted(have) == sorted(wanted) and not force:
        return
    for k in [k for k in knobs if k.startswith(LINK_PREFIX) or k == "pl_out_div"]:
        try:
            node.removeKnob(node[k])
        except Exception:
            pass
    knobs = node.knobs()
    node.addKnob(nuke.Text_Knob("pl_out_div", "Output"))
    for name in COMMON_KNOBS + FORMAT_KNOBS + RANGE_KNOBS:
        if name not in knobs:
            continue
        src = knobs[name]
        lk = nuke.Link_Knob(LINK_PREFIX + name, src.label() or name)
        lk.makeLink(node.fullName(), name)
        if name in ("first", "last") or (name == "Render" and "last" in knobs):
            lk.clearFlag(nuke.STARTLINE)
        node.addKnob(lk)


def _before_render():
    """Claim/lock version, confirm overwrite when frames exist, create folders."""
    node = nuke.thisNode()
    if "pl_version" not in node.knobs():
        return
    root = _root(node)
    claim = True
    try:
        claim = bool(node["pl_claim"].value()) if "pl_claim" in node.knobs() else True
    except Exception:
        claim = True
    parent = _type_dir(node)
    preferred = node["pl_version"].value()
    if claim:
        ver, vdir, _ = cfg.claim_version(parent, preferred, source_app="nuke")
        # point Write at claimed version path
        if "pl_version" in node.knobs():
            # temporarily set concrete version for path build
            values = list(node["pl_version"].values())
            if ver not in values:
                _set_menu(node["pl_version"], [NEW, ver] + [v for v in values if v not in (NEW, ver)])
            node["pl_version"].setValue(ver)
        update_path(node, rescan_versions=False)
    else:
        update_path(node)
        ver = node["pl_version"].value()
        if ver == NEW:
            ver = _next_version(node)
        vdir = "%s/%s" % (parent, ver if ver != NEW else _next_version(node))

    path = nuke.filename(node) or ""
    vdir = cfg.norm_path(os.path.dirname(path) if path else vdir)
    if cfg.version_has_frames(vdir):
        settings = cfg.show_settings(root)
        confirm = settings.get("confirm_overwrite", not settings.get("allow_overwrite", False))
        allow = False
        try:
            allow = bool(node["pl_allow_overwrite"].value()) if "pl_allow_overwrite" in node.knobs() else False
        except Exception:
            allow = False
        if confirm and not allow:
            if nuke.GUI:
                if not nuke.ask("PAAI Pipeline\n\nOverwrite existing frames in %s?\n%s" % (ver, path)):
                    raise RuntimeError("PAAI Pipeline: Render cancelled: not overwriting %s" % ver)
            else:
                raise RuntimeError("PAAI Pipeline: Render cancelled: not overwriting %s (enable Allow Overwrite)" % ver)
    if path:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)


def _after_render():
    """Write unified version_note.json; keep Version on New for next bump."""
    node = nuke.thisNode()
    if "pl_version" in node.knobs():
        path = nuke.filename(node)
        if path:
            try:
                ft = node["file_type"].value()
            except Exception:
                ft = ""
            try:
                bd = node["datatype"].value() if "datatype" in node.knobs() else ""
            except Exception:
                bd = ""
            try:
                comp = node["compression"].value() if "compression" in node.knobs() else ""
            except Exception:
                comp = ""
            cfg.write_note(
                os.path.dirname(path), node["pl_note"].value(),
                source="nuke",
                frames="%d-%d" % (nuke.root().firstFrame(), nuke.root().lastFrame()),
                format=ft, bit_depth=str(bd), compression=str(comp),
                script=nuke.root().name(),
                version=node["pl_version"].value(),
                sequence=node["pl_sequence"].value(),
                shot=node["pl_shot"].value(),
                type=node["pl_type"].value(),
                name=_elem_name(node),
            )
        # return dropdown to New after a claimed concrete version render
        try:
            if node["pl_version"].value() != NEW:
                refresh_versions(node)
                node["pl_version"].setValue(NEW)
        except Exception:
            pass
        update_path(node)


def load_note(node):
    """Show the saved note when an existing version is picked."""
    ver = node["pl_version"].value()
    if ver != NEW:
        node["pl_note"].setValue(cfg.read_note("%s/%s" % (_type_dir(node), ver)).get("note", ""))


_busy = False


def _knob_changed():
    """Any change on the Pipeline tab rebuilds the Write's file path right away."""
    global _busy
    node, knob = nuke.thisNode(), nuke.thisKnob()
    if _busy or "pl_sequence" not in node.knobs():
        return
    name = knob.name()
    _busy = True
    try:
        if name in ("pl_root", "pl_sequence", "pl_shot", "pl_type", "pl_name", "pl_version"):
            node["pl_custom"].setValue(False)
        if name in ("pl_root", "pl_sequence", "pl_shot", "pl_type", "pl_name"):
            # different shot/type/name: go back to New so you never overwrite by accident
            node["pl_version"].setValue(NEW)
        if name == "pl_type":
            set_type_filetype(node)
        if name in ("pl_root", "showPanel"):
            refresh_sequences(node)
            if name == "showPanel":
                build_output_links(node)
        elif name == "pl_sequence":
            refresh_shots(node)
        elif name in ("pl_shot", "pl_type", "pl_name"):
            update_path(node)
        elif name == "pl_version":
            update_path(node, rescan_versions=False)
            load_note(node)
        elif name == "file_type":
            update_path(node, rescan_versions=False)   # new extension
            build_output_links(node)                   # show that format's settings
        elif name == "name":
            build_output_links(node, force=True)       # node renamed: re-point links
        elif name == "file":
            # typed or pasted a pipeline path on the Write tab: update the dropdowns to match
            if parse_path(node["file"].value()):
                node["pl_custom"].setValue(False)
                sync_from_path(node)
    except Exception as e:
        nuke.tprint("PAAI Pipeline: %s" % e)
    finally:
        _busy = False


_PATTERNS = [
    re.compile(r"^(?P<root>.*)/(?P<seq>[^/]+)/(?P<shot>[^/]+)/(?P<sub>[^/]+)/(?P<type>[^/]+)/"
               r"(?P<name>[^/]+)/(?P<ver>v\d+)/[^/]+$"),
    re.compile(r"^(?P<root>.*)/(?P<seq>[^/]+)/(?P<shot>[^/]+)/(?P<sub>[^/]+)/(?P<type>[^/]+)/"
               r"(?P<ver>v\d+)/[^/]+$"),
]


def _force(knob, value):
    """Set an Enumeration knob even if the value is not in its list yet."""
    vals = list(knob.values())
    if value not in vals:
        knob.setValues(vals + [value] if vals != [NONE] else [value])
    knob.setValue(value)


def parse_path(path):
    """Pipeline path -> dict(root, seq, shot, type, name, ver) or None.
    The render folder (e.g. paai) must match that show's show_config.txt."""
    path = (path or "").replace("\\", "/")
    for pat in _PATTERNS:
        m = pat.match(path)
        if not m:
            continue
        info = m.groupdict()
        info.setdefault("name", None)
        if info["sub"] != cfg.render_subdir(info["root"]):
            continue
        return info
    return None


def sync_from_path(node):
    """Set the dropdowns from the Write's existing file path. Returns True if it matched."""
    info = parse_path(node["file"].value())
    if not info:
        return False
    node["pl_root"].setValue(info["root"])
    _set_menu(node["pl_sequence"], list(cfg.list_shots(info["root"])))
    _force(node["pl_sequence"], info["seq"])
    _set_menu(node["pl_shot"], cfg.list_shots(info["root"]).get(info["seq"], []))
    refresh_types(node)
    _force(node["pl_shot"], info["shot"])
    _force(node["pl_type"], info["type"])
    node["pl_name"].setValue(info["name"] or "")
    ext = node["file"].value().rsplit(".", 1)[-1].lower()
    try:
        node["file_type"].setValue({"jpg": "jpeg", "tif": "tiff"}.get(ext, ext))
    except Exception:
        pass
    refresh_versions(node)
    _force(node["pl_version"], info["ver"])
    load_note(node)
    update_path(node, rescan_versions=False)
    return True


def apply_last_used(node):
    """Fill a fresh Write from the Render Browser's last root / sequence / shot / type."""
    prefs = cfg.load_prefs()
    node["pl_root"].setValue(cfg.start_root() or (nuke.root()["project_directory"].value() or ""))
    _set_menu(node["pl_sequence"], list(cfg.list_shots(_root(node))))
    refresh_types(node)
    if prefs.get("seq") in node["pl_sequence"].values():
        node["pl_sequence"].setValue(prefs["seq"])
    _set_menu(node["pl_shot"], cfg.list_shots(_root(node)).get(node["pl_sequence"].value(), []))
    if prefs.get("shot") in node["pl_shot"].values():
        node["pl_shot"].setValue(prefs["shot"])
    if prefs.get("type") in node["pl_type"].values():
        node["pl_type"].setValue(prefs["type"])
    set_type_filetype(node)
    update_path(node)


def add_pipeline_knobs(node=None):
    """Add the Pipeline tab to Nuke's Write node (safe to call twice).

    If the Write already has a pipeline path, the dropdowns are set to match it.
    If it has some other path, the path is left alone.
    If it is empty, it is filled from the last sequence / shot used in the Render Browser.
    """
    node = node or nuke.thisNode()
    if node.Class() != "Write" or "pl_sequence" in node.knobs():
        return node
    existing = node["file"].value()

    node.addKnob(nuke.Tab_Knob("pl_tab", TAB))
    node.addKnob(nuke.File_Knob("pl_root", "Project root"))
    node.addKnob(nuke.Enumeration_Knob("pl_sequence", "Sequence", [NONE]))
    node.addKnob(nuke.Enumeration_Knob("pl_shot", "Shot", [NONE]))
    node.addKnob(nuke.Enumeration_Knob("pl_type", "Render type", [t[0] for t in cfg.DEFAULT_TYPES]))
    node["pl_type"].setValue(cfg.default_type(cfg.start_root() or "", "precomp") or "precomp")
    name = nuke.String_Knob("pl_name", "Name")
    name.setTooltip("Every render type has name folders, each with its own versions:\n"
                    "<type>/<name>/v###   e.g. precomp/keying/v003\nEmpty = main")
    node.addKnob(name)

    ver = nuke.Enumeration_Knob("pl_version", "Version", [NEW])
    ver.setTooltip("New = create the next version on every render.\n"
                   "Pick an existing version to overwrite it.")
    node.addKnob(ver)
    claim = nuke.Boolean_Knob("pl_claim", "Claim")
    claim.setValue(True)
    claim.setTooltip("When on, atomically reserve the version folder (.claim). "
                     "If taken, bump to the next free version.")
    claim.setFlag(nuke.STARTLINE)
    node.addKnob(claim)
    allow = nuke.Boolean_Knob("pl_allow_overwrite", "Allow Overwrite")
    allow.setValue(False)
    allow.setTooltip("Allow writing into a version that already has frames.")
    node.addKnob(allow)
    note = nuke.Multiline_Eval_String_Knob("pl_note", "Version note")
    note.setTooltip("Saved with the version when you render. Shown in the Render Browser.")
    node.addKnob(note)

    node.addKnob(nuke.PyScript_Knob("pl_refresh", "Rescan folders",
                 "import pipeline_write; pipeline_write.refresh_sequences(nuke.thisNode())"))
    br = nuke.PyScript_Knob("pl_browse", "Render Browser",
                            "import render_browser; render_browser.show()")
    br.clearFlag(nuke.STARTLINE)
    node.addKnob(br)
    node.addKnob(nuke.Text_Knob("pl_info", ""))
    custom = nuke.Boolean_Knob("pl_custom", "keep custom path")
    custom.setFlag(nuke.INVISIBLE)
    node.addKnob(custom)

    try:
        if existing and not sync_from_path(node):
            node["pl_root"].setValue(cfg.start_root())
            node["pl_custom"].setValue(True)
            node["pl_info"].setValue("<font color=gray>Custom path kept. Pick a sequence/shot to switch to pipeline.</font>")
        elif not existing:
            apply_last_used(node)
    except Exception as e:
        nuke.tprint("PAAI Pipeline: %s" % e)
    build_output_links(node)
    return node


def setup_all_writes():
    """Add the Pipeline tab to every Write in the script, matching their current paths."""
    for n in nuke.allNodes("Write", recurseGroups=True):
        add_pipeline_knobs(n)


def set_writes_from_browser(seq, shot, root=None, nodes=None):
    """Point the given (or selected) pipeline Writes at seq/shot from the browser."""
    nodes = nodes or [n for n in nuke.selectedNodes() if n.Class() == "Write"]
    for n in nodes:
        add_pipeline_knobs(n)
        n["pl_custom"].setValue(False)
        if root:
            n["pl_root"].setValue(root)
            _set_menu(n["pl_sequence"], list(cfg.list_shots(root)))
            refresh_types(n)
        _force(n["pl_sequence"], seq)
        _set_menu(n["pl_shot"], cfg.list_shots(_root(n)).get(seq, []))
        _force(n["pl_shot"], shot)
        update_path(n)
    return nodes


def add_to_selected():
    """For old scripts: add the Pipeline tab to the selected Write nodes."""
    writes = [n for n in nuke.selectedNodes() if n.Class() == "Write"]
    for n in writes:
        add_pipeline_knobs(n)
    if not writes:
        nuke.message("PAAI Pipeline\n\nSelect one or more Write nodes.")


def _global_before_render():
    if "pl_version" in nuke.thisNode().knobs():
        _before_render()


def _global_after_render():
    if "pl_version" in nuke.thisNode().knobs():
        _after_render()


# Writes in scripts you open get the tab too, matched to their existing paths.
nuke.addOnScriptLoad(setup_all_writes)
# Every new Write node (W key, Tab menu, toolbar) gets the Pipeline tab.
nuke.addOnUserCreate(add_pipeline_knobs, nodeClass="Write")
nuke.addKnobChanged(_knob_changed, nodeClass="Write")
# Render hooks run globally, so each node's own beforeRender/afterRender knob stays free for you.
nuke.addBeforeRender(_global_before_render, nodeClass="Write")
nuke.addAfterRender(_global_after_render, nodeClass="Write")
