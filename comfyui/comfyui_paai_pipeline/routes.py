"""HTTP routes for the PAAI Render Browser and node combo refresh."""
import os
import subprocess
import sys

from . import pipeline_config as cfg
from . import scan
from . import choices
from . import image_io

try:
    from aiohttp import web
except Exception:  # pragma: no cover
    web = None


def _json(data, status=200):
    return web.json_response(data, status=status)


def _root(req, body=None):
    if body and body.get("root"):
        return (body.get("root") or "").strip()
    return (req.rel_url.query.get("root") or "").strip()


def setup_routes():
    """Register /paai/* on ComfyUI's PromptServer. Safe if server missing (tests)."""
    try:
        from server import PromptServer
    except Exception:
        return False
    if web is None:
        return False
    server = PromptServer.instance
    r = server.routes

    @r.get("/paai/ping")
    async def ping(req):
        return _json({"ok": True, "pack": "comfyui_paai_pipeline"})

    @r.get("/paai/prefs")
    async def get_prefs(req):
        prefs = cfg.load_prefs()
        try:
            root = prefs.get("root") or ""
            if root:
                prefs["render_queue_path"] = cfg.render_queue_path(root)
                prefs["start_frame"] = cfg.start_frame(root)
        except Exception:
            pass
        try:
            from . import paai_queue_link as link
            qp = prefs.get("render_queue_path") or ""
            prefs["queue_url"] = link.discover_url(queue_path=qp, show_root=prefs.get("root") or "")
        except Exception:
            pass
        return _json(prefs)

    @r.get("/paai/queue_url")
    async def queue_url(req):
        """Discover the live Render Queue URL without importing paai_render_queue."""
        from . import paai_queue_link as link
        q = getattr(req, "rel_url", None)
        qp = ""
        root = ""
        try:
            qp = (q.query.get("queue_path") if q is not None else "") or ""
            root = (q.query.get("root") if q is not None else "") or ""
        except Exception:
            pass
        if not qp:
            prefs = cfg.load_prefs()
            qp = prefs.get("render_queue_path") or ""
            root = root or prefs.get("root") or ""
        url = link.discover_url(queue_path=qp, show_root=root)
        ping = link.ping(url=url)
        return _json({"ok": bool(ping.get("ok")), "url": url, "message": ping.get("message", "")})


    @r.post("/paai/show/create")
    async def show_create(req):
        from . import paai_show
        body = await req.json()
        root = (body.get("root") or "").strip()
        seq = (body.get("sequence") or body.get("seq") or "").strip()
        shots = (body.get("shots") or "").strip()
        pairs = paai_show._parse_shots_arg(seq, shots)
        for tok in body.get("seq_shots") or []:
            pairs += paai_show._parse_seq_shots_token(tok)
        if not root or not pairs:
            return _json({"ok": False, "error": "root and shots required"}, 400)
        result = paai_show.create_show(root, pairs, quiet=True)
        code, lines = paai_show.check_show(root, quiet=True)
        try:
            cfg.save_prefs(root=cfg.norm_path(root))
        except Exception:
            pass
        return _json({"ok": code < 2, "result": result, "check": lines, "exit_code": code})

    @r.post("/paai/show/check")
    async def show_check(req):
        from . import paai_show
        body = await req.json()
        root = (body.get("root") or "").strip()
        if not root:
            return _json({"ok": False, "error": "root required"}, 400)
        code, lines = paai_show.check_show(root, quiet=True)
        return _json({"ok": code < 2, "check": lines, "exit_code": code})

    @r.post("/paai/prefs")
    async def post_prefs(req):
        body = await req.json()
        cfg.save_prefs(**{k: v for k, v in body.items() if k != "root" or v})
        if body.get("root") is not None:
            cfg.save_prefs(root=body.get("root"))
        return _json({"ok": True, "prefs": cfg.load_prefs()})

    @r.get("/paai/scan")
    async def do_scan(req):
        root = _root(req)
        if not root or not os.path.isdir(root):
            return _json({"ok": False, "error": "root not found", "root": root}, 400)
        cfg.ensure_config(root)
        items = list(scan.scan_renders(root))
        shots = scan.scan_tree(root)
        names = cfg.list_names(root, {(i["type"], i["name"]) for i in items})
        types = cfg.render_types(root)
        cfg.save_prefs(root=root)
        return _json({
            "ok": True, "root": root, "items": items,
            "shots": shots, "names": names, "types": types,
            "prefs": cfg.load_prefs(),
            "config_dir": cfg.config_dir(root),
        })

    @r.get("/paai/config")
    async def get_config(req):
        root = _root(req)
        if not root:
            return _json({"ok": False, "error": "root required"}, 400)
        d = cfg.ensure_config(root)
        return _json({
            "ok": True, "config_dir": d,
            "settings": cfg.show_settings(root),
            "types": [{"name": n, "ext": e, "named": named} for n, e, named in cfg._types(root)],
            "shots": cfg.list_shots(root),
            "names": cfg.list_names(root),
        })

    @r.post("/paai/add_shot")
    async def add_shot(req):
        body = await req.json()
        root = (body.get("root") or "").strip()
        seq = (body.get("seq") or body.get("sequence") or "").strip()
        shots = body.get("shots") or body.get("shot") or ""
        if isinstance(shots, str):
            shots = [x.strip() for x in shots.replace(";", ",").split(",") if x.strip()]
        make = bool(body.get("make_folders", True))
        if not root or not seq or not shots:
            return _json({"ok": False, "error": "root, seq, shots required"}, 400)
        for sh in shots:
            cfg.add_shot(root, seq, sh, make_folders=make)
        return _json({"ok": True, "shots": cfg.list_shots(root)})

    @r.post("/paai/add_type")
    async def add_type(req):
        body = await req.json()
        root = (body.get("root") or "").strip()
        name = (body.get("name") or "").strip().replace(" ", "_")
        ext = (body.get("ext") or "exr").strip().lstrip(".")
        named = bool(body.get("named", False))
        if not root or not name:
            return _json({"ok": False, "error": "root and name required"}, 400)
        ok = cfg.add_type(root, name, ext, named)
        if ok:
            cfg.add_name(root, name, "main")
        return _json({"ok": ok, "types": cfg.render_types(root),
                      "names": cfg.list_names(root)})

    @r.get("/paai/note")
    async def get_note(req):
        folder = (req.rel_url.query.get("folder") or "").strip()
        if not folder:
            return _json({"ok": False, "error": "folder required"}, 400)
        return _json({"ok": True, "note": cfg.read_note(folder)})

    @r.post("/paai/note")
    async def post_note(req):
        body = await req.json()
        folder = (body.get("folder") or "").strip()
        note = body.get("note", "")
        if not folder:
            return _json({"ok": False, "error": "folder required"}, 400)
        cfg.write_note(folder, note)
        return _json({"ok": True, "note": cfg.read_note(folder)})

    @r.post("/paai/open_folder")
    async def open_folder(req):
        body = await req.json()
        path = (body.get("path") or body.get("folder") or "").strip()
        if not path or not os.path.exists(path):
            return _json({"ok": False, "error": "path not found"}, 400)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return _json({"ok": True})
        except Exception as e:
            return _json({"ok": False, "error": str(e)}, 500)

    @r.get("/paai/versions")
    async def versions(req):
        q = req.rel_url.query
        root, seq, shot = q.get("root", ""), q.get("sequence", ""), q.get("shot", "")
        rtype, name = q.get("type", ""), q.get("name", "main")
        if not (root and seq and shot and rtype):
            return _json({"ok": False, "error": "root/sequence/shot/type required"}, 400)
        vers = scan.existing_versions(root, seq, shot, rtype, name)
        nxt = scan.next_version(root, seq, shot, rtype, name)
        return _json({"ok": True, "versions": ["New"] + vers, "next": nxt})

    @r.get("/paai/dropdowns")
    async def dropdowns(req):
        """Populate Load/Write combo boxes from disk."""
        q = req.rel_url.query
        d = choices.dropdowns(q.get("root") or "", q.get("sequence") or "", q.get("shot") or "",
                              q.get("type") or "", q.get("name") or "", for_load=q.get("kind") == "load")
        if not d:
            return _json({"ok": False, "error": "root not found", "root": q.get("root")}, 400)
        d["ok"] = True
        d["formats"] = choices.FORMATS
        return _json(d)

    @r.get("/paai/layers")
    async def layers(req):
        q = req.rel_url.query
        path = (q.get("path") or "").strip()
        root, seq, shot = q.get("root", ""), q.get("sequence", ""), q.get("shot", "")
        rtype, name, ver = q.get("type", ""), q.get("name", "main"), q.get("version", "")
        if not path and root and seq and shot and rtype and ver and ver != "New":
            vdir = os.path.join(scan.type_dir(root, seq, shot, rtype, name), ver)
            seqs = scan.find_sequences(vdir)
            if seqs:
                # pick first frame file
                files = scan.resolve_frame_files(seqs[0][0])
                path = files[0][1] if files else ""
            else:
                path = ""
        if not path or not os.path.isfile(path):
            # try with # replaced by first existing
            if path and "#" in path:
                files = scan.resolve_frame_files(path)
                path = files[0][1] if files else ""
        if not path or not os.path.isfile(path):
            return _json({"ok": True, "layers": ["rgba"], "path": path})
        return _json({"ok": True, "layers": image_io.list_exr_layers(path), "path": path})

    @r.get("/paai/preview_path")
    async def preview_path(req):
        q = req.rel_url.query
        root = q.get("root", "")
        seq, shot, rtype = q.get("sequence", ""), q.get("shot", ""), q.get("type", "comfyui")
        name, ver = q.get("name", "main"), q.get("version", "New")
        ext = q.get("ext") or cfg.type_ext(root, rtype)
        if not (root and seq and shot and rtype):
            return _json({"ok": False, "path": "", "info": "pick sequence/shot"})
        is_new = ver == "New" or not ver
        real = scan.next_version(root, seq, shot, rtype, name) if is_new else ver
        path = scan.build_path(root, seq, shot, rtype, name, real, ext)
        info = ("NEW version  %s | %s | %s_%s | %s" % (seq, shot, rtype, name, real)
                if is_new else
                "OVERWRITE  %s | %s | %s_%s | %s" % (seq, shot, rtype, name, real))
        return _json({"ok": True, "path": path, "version": real, "info": info, "is_new": is_new})

    return True
