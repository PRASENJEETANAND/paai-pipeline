"""Local HTTP Render Browser fallback (stdlib http.server + webbrowser).

Actions from the page are queued and drained on the Blender main thread via bpy.app.timers.
"""
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

from . import pipeline_config as cfg
from . import scan

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
_ACTION_Q = queue.Queue()
_SERVER = None
_THREAD = None
_PORT = None
_TIMER_RUNNING = False


def enqueue(action):
    _ACTION_Q.put(action)


def _drain_actions():
    """Timer callback: run queued bpy operators on the main thread."""
    global _TIMER_RUNNING
    try:
        import bpy
        while True:
            try:
                act = _ACTION_Q.get_nowait()
            except queue.Empty:
                break
            try:
                kind = act.get("action")
                if kind == "set_as_output":
                    bpy.ops.paai.set_as_output(
                        root=act.get("root", ""),
                        sequence=act.get("seq", ""),
                        shot=act.get("shot", ""),
                        render_type=act.get("type", ""),
                        name=act.get("name", "main"),
                        version=act.get("version", "New"),
                    )
                elif kind == "load_as_image":
                    kwargs = dict(path=act.get("path", ""), name=act.get("name", ""))
                    if act.get("first") is not None:
                        kwargs["first"] = int(act["first"])
                    if act.get("last") is not None:
                        kwargs["last"] = int(act["last"])
                    bpy.ops.paai.load_as_image(**kwargs)
            except Exception as e:
                print("[PAAI] action failed:", e, act)
    except Exception as e:
        print("[PAAI] drain:", e)
    # keep timer alive while server runs
    if _SERVER is not None:
        return 0.25
    _TIMER_RUNNING = False
    return None


def _ensure_timer():
    global _TIMER_RUNNING
    if _TIMER_RUNNING:
        return
    try:
        import bpy
        bpy.app.timers.register(_drain_actions, first_interval=0.25)
        _TIMER_RUNNING = True
    except Exception as e:
        print("[PAAI] timer:", e)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # quiet

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, data, content_type="text/html"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        path = unquote(u.path)
        qs = {k: v[0] if v else "" for k, v in parse_qs(u.query).items()}

        if path in ("/", "/index.html"):
            return self._serve_file("index.html", "text/html; charset=utf-8")
        if path.endswith(".css"):
            return self._serve_file(os.path.basename(path), "text/css; charset=utf-8")
        if path.endswith(".js"):
            return self._serve_file(os.path.basename(path), "application/javascript; charset=utf-8")
        if path.endswith(".png"):
            return self._serve_file(os.path.basename(path), "image/png")

        if path == "/paai/ping":
            return self._json({"ok": True, "pack": "blender_paai_pipeline"})
        if path == "/paai/prefs":
            return self._json(cfg.load_prefs())
        if path == "/paai/scan":
            root = (qs.get("root") or "").strip()
            if not root or not os.path.isdir(root):
                return self._json({"ok": False, "error": "root not found", "root": root}, 400)
            cfg.ensure_config(root)
            items = list(scan.scan_renders(root))
            shots = scan.scan_tree(root)
            names = cfg.list_names(root, {(i["type"], i["name"]) for i in items})
            cfg.save_prefs(root=root)
            return self._json({
                "ok": True, "root": root, "items": items,
                "shots": shots, "names": names, "types": cfg.render_types(root),
                "prefs": cfg.load_prefs(), "config_dir": cfg.config_dir(root),
            })
        if path == "/paai/config":
            root = (qs.get("root") or "").strip()
            if not root:
                return self._json({"ok": False, "error": "root required"}, 400)
            d = cfg.ensure_config(root)
            return self._json({
                "ok": True, "config_dir": d,
                "settings": cfg.show_settings(root),
                "types": [{"name": n, "ext": e, "named": named} for n, e, named in cfg._types(root)],
                "shots": cfg.list_shots(root), "names": cfg.list_names(root),
            })
        if path == "/paai/note":
            folder = (qs.get("folder") or "").strip()
            return self._json({"ok": True, "note": cfg.read_note(folder)})
        self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        path = unquote(u.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            body = {}

        if path == "/paai/prefs":
            cfg.save_prefs(**{k: v for k, v in body.items() if v is not None})
            return self._json({"ok": True, "prefs": cfg.load_prefs()})
        if path == "/paai/add_shot":
            root = (body.get("root") or "").strip()
            seq = (body.get("seq") or body.get("sequence") or "").strip()
            shots = body.get("shots") or body.get("shot") or ""
            if isinstance(shots, str):
                shots = [x.strip() for x in shots.replace(";", ",").split(",") if x.strip()]
            make = bool(body.get("make_folders", True))
            if not root or not seq or not shots:
                return self._json({"ok": False, "error": "root, seq, shots required"}, 400)
            for sh in shots:
                cfg.add_shot(root, seq, sh, make_folders=make)
            return self._json({"ok": True, "shots": cfg.list_shots(root)})
        if path == "/paai/add_type":
            root = (body.get("root") or "").strip()
            name = (body.get("name") or "").strip().replace(" ", "_")
            ext = (body.get("ext") or "exr").strip().lstrip(".")
            named = bool(body.get("named", False))
            if not root or not name:
                return self._json({"ok": False, "error": "root and name required"}, 400)
            ok = cfg.add_type(root, name, ext, named)
            if ok:
                cfg.add_name(root, name, "main")
            return self._json({"ok": ok, "types": cfg.render_types(root), "names": cfg.list_names(root)})
        if path == "/paai/note":
            folder = (body.get("folder") or "").strip()
            note = body.get("note", "")
            if not folder:
                return self._json({"ok": False, "error": "folder required"}, 400)
            cfg.write_note(folder, note)
            return self._json({"ok": True, "note": cfg.read_note(folder)})
        if path == "/paai/open_folder":
            p = (body.get("path") or body.get("folder") or "").strip()
            if not p or not os.path.exists(p):
                return self._json({"ok": False, "error": "path not found"}, 400)
            try:
                if sys.platform.startswith("win"):
                    os.startfile(p)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", p])
                else:
                    subprocess.Popen(["xdg-open", p])
                return self._json({"ok": True})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)}, 500)
        if path == "/paai/action":
            enqueue(body)
            _ensure_timer()
            return self._json({"ok": True, "queued": True})
        self._json({"ok": False, "error": "not found"}, 404)

    def _serve_file(self, name, content_type):
        fp = os.path.join(WEB_DIR, name)
        if not os.path.isfile(fp):
            return self._json({"ok": False, "error": "missing " + name}, 404)
        with open(fp, "rb") as f:
            data = f.read()
        self._bytes(data, content_type)


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(open_browser=True):
    """Start (or reuse) the local server and optionally open the system browser."""
    global _SERVER, _THREAD, _PORT
    if _SERVER is None:
        _PORT = _free_port()
        _SERVER = ThreadingHTTPServer(("127.0.0.1", _PORT), Handler)
        _THREAD = threading.Thread(target=_SERVER.serve_forever, daemon=True)
        _THREAD.start()
        _ensure_timer()
        print("[PAAI] Render Browser at http://127.0.0.1:%d/" % _PORT)
    url = "http://127.0.0.1:%d/" % _PORT
    if open_browser:
        webbrowser.open(url)
    return url


def stop():
    global _SERVER, _THREAD, _PORT
    if _SERVER is not None:
        try:
            _SERVER.shutdown()
        except Exception:
            pass
        _SERVER = None
        _THREAD = None
        _PORT = None


def show(context=None):
    return start(open_browser=True)
