"""HTTP API + static web UI for PAAI Render Queue."""
from __future__ import annotations
import json
import os
import mimetypes
import traceback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

from . import config
from . import executors
from .store import JobStore
from .scheduler import Scheduler

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


class AppState:
    def __init__(self):
        self.settings = config.load_settings()
        self.store = JobStore(config.queue_dir(self.settings))
        self.scheduler = Scheduler(self.store, self.settings)
        self.scheduler.start()  # tick thread always on (per-job Start works while stopped)
        if self.settings.get("auto_start"):
            self.scheduler.start_queue()

    def reload_settings(self, new_settings=None, move_data=False):
        old_home = config.data_home(self.settings)
        if new_settings is not None:
            # apply, possibly changing data_folder
            incoming = dict(new_settings)
            new_home = (incoming.get("data_folder") or "").strip()
            if new_home:
                new_home = os.path.abspath(os.path.expanduser(new_home))
                if move_data and new_home != old_home and os.path.isdir(old_home):
                    config.move_data(old_home, new_home)
                incoming["data_folder"] = new_home
            self.settings.update(incoming)
            # Migration: obsolete showset_root from early builds
            self.settings.pop("showset_root", None)
            self.settings.pop("queue_folder", None)
            config.save_settings(self.settings)
        else:
            self.settings = config.load_settings()
        q = config.queue_dir(self.settings)
        if q != self.store.root:
            self.store = JobStore(q)
            self.scheduler.store = self.store
        self.scheduler.update_settings(self.settings)
        return self.settings


STATE = None


def get_state() -> AppState:
    global STATE
    if STATE is None:
        STATE = AppState()
    return STATE


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
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

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        try:
            self._do_GET()
        except Exception as e:
            self._json({"ok": False, "error": str(e), "trace": traceback.format_exc()}, 500)

    def do_POST(self):
        try:
            self._do_POST()
        except Exception as e:
            self._json({"ok": False, "error": str(e), "trace": traceback.format_exc()}, 500)

    def do_DELETE(self):
        try:
            self._do_DELETE()
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)

    def _serve_static(self, path):
        path = unquote(path)
        if path in ("/", "/index.html"):
            return self._file(os.path.join(WEB_DIR, "index.html"), "text/html; charset=utf-8")
        name = os.path.basename(path)
        for folder, ctype_map in (
            (WEB_DIR, {".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8",
                       ".html": "text/html; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml"}),
            (STATIC_DIR, {".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml"}),
        ):
            fp = os.path.join(folder, name)
            if os.path.isfile(fp):
                ext = os.path.splitext(name)[1].lower()
                ctype = ctype_map.get(ext) or mimetypes.guess_type(fp)[0] or "application/octet-stream"
                return self._file(fp, ctype)
        self._json({"ok": False, "error": "not found"}, 404)

    def _file(self, fp, ctype):
        with open(fp, "rb") as f:
            data = f.read()
        self._bytes(data, ctype)

    def _do_GET(self):
        u = urlparse(self.path)
        path = unquote(u.path)
        qs = {k: (v[0] if v else "") for k, v in parse_qs(u.query).items()}
        st = get_state()

        if path.startswith("/api/"):
            return self._api_get(path, qs, st)
        return self._serve_static(path)

    def _api_get(self, path, qs, st):
        if path == "/api/ping":
            return self._json({"ok": True, "service": "paai_render_queue", "version": "1.0.0"})
        if path == "/api/settings":
            return self._json({"ok": True, "settings": st.settings, "scheduler": st.scheduler.status(),
                              "documents_dir": config.documents_dir(),
                              "default_data_folder": config.resolve_default_data_home(),
                              "pointer": config.POINTER_FILE})
        if path == "/api/jobs":
            return self._json({"ok": True, "jobs": st.store.list_jobs(), "scheduler": st.scheduler.status()})
        if path.startswith("/api/jobs/"):
            parts = path.strip("/").split("/")
            # /api/jobs/<id> or /api/jobs/<id>/log
            if len(parts) >= 3:
                jid = parts[2]
                job = st.store.get(jid)
                if not job:
                    return self._json({"ok": False, "error": "not found"}, 404)
                if len(parts) >= 4 and parts[3] == "log":
                    tail = int(qs.get("tail") or 200)
                    log = ""
                    lp = job.get("log_path") or ""
                    if lp and os.path.isfile(lp):
                        with open(lp, "r", errors="replace") as f:
                            lines = f.readlines()
                        log = "".join(lines[-tail:])
                    return self._json({"ok": True, "log": log, "path": lp})
                return self._json({"ok": True, "job": job})
        if path == "/api/open_folder":
            # GET ?path=
            p = qs.get("path") or ""
            if p and os.path.exists(p):
                _open_path(p)
                return self._json({"ok": True})
            return self._json({"ok": False, "error": "missing path"}, 400)
        self._json({"ok": False, "error": "not found"}, 404)

    def _do_POST(self):
        u = urlparse(self.path)
        path = unquote(u.path)
        body = self._read_json()
        st = get_state()

        if path == "/api/settings":
            moved = bool(body.get("move_data"))
            st.reload_settings(body.get("settings") or body, move_data=moved)
            return self._json({"ok": True, "settings": st.settings, "path": config.settings_path(),
                              "pointer": config.POINTER_FILE, "data_folder": config.data_home(st.settings)})

        if path == "/api/test_launcher":
            kind = body.get("kind") or "blender"
            path_ = body.get("path") or ""
            return self._json({"ok": True, "result": executors.test_launcher(path_, kind)})

        if path == "/api/test_comfy":
            url = (body.get("url") or "").rstrip("/")
            return self._json({"ok": True, "result": executors.test_launcher(url, "comfyui")})

        if path == "/api/jobs":
            # submit one or many
            items = body.get("jobs") or ([body] if body.get("app") or body.get("name") else [])
            created = []
            for item in items:
                src = item.get("source_file") or ""
                copy_from = item.pop("copy_from", None) or item.get("extra", {}).get("copy_from")
                if copy_from and os.path.isfile(copy_from):
                    ext = os.path.splitext(copy_from)[1] or ".dat"
                    src = st.store.save_script_copy(copy_from, item.get("app") or "job", ext)
                    item["source_file"] = src
                job = st.store.create(**item)
                created.append(job)
            if st.settings.get("auto_start"):
                st.scheduler.start_queue()
            return self._json({"ok": True, "jobs": created, "scheduler": st.scheduler.status()})

        if path.startswith("/api/jobs/"):
            parts = path.strip("/").split("/")
            if len(parts) < 4:
                return self._json({"ok": False, "error": "action required"}, 400)
            jid, action = parts[2], parts[3]
            job = st.store.get(jid)
            if not job and action != "delete":
                return self._json({"ok": False, "error": "not found"}, 404)
            if action in ("cancel", "kill"):
                return self._json({"ok": True, "job": st.scheduler.kill_job(jid)})
            if action == "start":
                return self._json({"ok": True, "job": st.scheduler.start_job(jid)})
            if action == "pause":
                return self._json({"ok": True, "job": st.scheduler.pause_job(jid)})
            if action == "resume":
                return self._json({"ok": True, "job": st.scheduler.resume_job(jid)})
            if action == "retry":
                return self._json({"ok": True, "job": st.scheduler.retry_job(jid)})
            if action == "priority":
                pr = int(body.get("priority", job.get("priority", 50)))
                return self._json({"ok": True, "job": st.store.update(jid, priority=pr)})
            if action == "delete":
                st.scheduler.cancel_job(jid)
                st.store.delete(jid, remove_files=bool(body.get("remove_files")))
                return self._json({"ok": True})
            if action == "open_output":
                p = (job.get("output_path") or os.path.dirname(job.get("source_file") or "") or "")
                if p:
                    _open_path(p)
                return self._json({"ok": True, "path": p})
            return self._json({"ok": False, "error": "unknown action"}, 400)

        if path == "/api/queue/start":
            return self._json({"ok": True, "scheduler": st.scheduler.start_queue()})
        if path == "/api/queue/stop":
            return self._json({"ok": True, "scheduler": st.scheduler.stop_queue()})
        if path == "/api/queue/pause":
            return self._json({"ok": True, "scheduler": st.scheduler.pause_queue(True)})
        if path == "/api/queue/resume":
            # resume from paused -> running
            return self._json({"ok": True, "scheduler": st.scheduler.pause_queue(False)})
        if path == "/api/queue/auto_start":
            val = bool(body.get("auto_start", True))
            st.settings["auto_start"] = val
            config.save_settings(st.settings)
            st.scheduler.update_settings(st.settings)
            if val:
                st.scheduler.start_queue()
            return self._json({"ok": True, "settings": st.settings, "scheduler": st.scheduler.status()})

        if path == "/api/open_folder":
            p = body.get("path") or ""
            if p and os.path.exists(p):
                _open_path(p)
                return self._json({"ok": True})
            return self._json({"ok": False, "error": "missing path"}, 400)

        self._json({"ok": False, "error": "not found"}, 404)

    def _do_DELETE(self):
        u = urlparse(self.path)
        path = unquote(u.path)
        st = get_state()
        if path.startswith("/api/jobs/"):
            jid = path.strip("/").split("/")[2]
            st.scheduler.cancel_job(jid)
            st.store.delete(jid)
            return self._json({"ok": True})
        self._json({"ok": False, "error": "not found"}, 404)


def _open_path(p):
    import subprocess, sys
    try:
        if sys.platform.startswith("win"):
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception:
        pass


def serve(host=None, port=None, root=None, data_folder=None):
    """root is accepted as an alias for data_folder (legacy CLI)."""
    global STATE
    home = data_folder or root
    if home:
        os.environ["PAAI_RQ_HOME"] = os.path.abspath(os.path.expanduser(home))
        config.write_pointer(os.environ["PAAI_RQ_HOME"])
    STATE = AppState()
    host = host or config.DEFAULT_HOST
    preferred = port if port is not None else STATE.settings.get("port") or config.DEFAULT_PORT
    port = config.pick_free_port(preferred, host=host)
    STATE.settings["port"] = int(port)
    try:
        config.save_settings(STATE.settings)
    except Exception:
        pass
    url = "http://%s:%d" % (host if host not in ("0.0.0.0", "") else "127.0.0.1", port)
    try:
        config.write_discovery(url, port, home=config.data_home(STATE.settings))
    except Exception as e:
        print("[PAAI RQ] discovery write failed:", e)
    print("[PAAI RQ] listening on %s  (data: %s)" % (url, config.data_home(STATE.settings)))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print("[PAAI RQ] http://%s:%d/  data=%s" % (host, port, STATE.store.root))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[PAAI RQ] shutting down")
        STATE.scheduler.stop()
        httpd.shutdown()
