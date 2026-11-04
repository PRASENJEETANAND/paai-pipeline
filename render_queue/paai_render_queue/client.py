"""Submit jobs to a running queue server, or drop JSON into the queue folder."""
from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request

from . import config
from .store import JobStore


DEFAULT_URL = "http://127.0.0.1:%d" % config.DEFAULT_PORT


def discover_url(show_root: str = None, queue_path: str = None, base_url: str = None) -> str:
    """Resolve queue URL: explicit > discovery files > settings port > default."""
    if base_url:
        return base_url.rstrip("/")
    extras = []
    if queue_path:
        extras.append(os.path.expanduser(queue_path))
        # if queue_path points at the paai_render_queue package parent, still try Documents
    if show_root:
        try:
            # late import avoidance: show_config may live outside; callers pass render_queue_path
            pass
        except Exception:
            pass
    disc = config.read_discovery(extra_homes=extras)
    if disc.get("url"):
        return str(disc["url"]).rstrip("/")
    settings = config.load_settings()
    port = int(settings.get("port") or config.DEFAULT_PORT)
    return "http://127.0.0.1:%d" % port


def server_url(settings=None):
    settings = settings or config.load_settings()
    disc = config.read_discovery(extra_homes=[settings.get("data_folder")])
    if disc.get("url"):
        return str(disc["url"]).rstrip("/")
    port = int(settings.get("port") or config.DEFAULT_PORT)
    return "http://127.0.0.1:%d" % port


def ping(base_url=None, timeout=1.5):
    base = (base_url or discover_url()).rstrip("/")
    try:
        with urllib.request.urlopen(base + "/api/ping", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def submit(jobs, base_url=None, settings=None, show_root=None, queue_path=None):
    """Submit list of job dicts. Returns {ok, jobs, mode: 'api'|'folder', message}."""
    settings = settings or config.load_settings()
    base = discover_url(show_root=show_root, queue_path=queue_path, base_url=base_url)
    if isinstance(jobs, dict):
        jobs = [jobs]
    payload = {"jobs": jobs}
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            base + "/api/jobs", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        data["mode"] = "api"
        data["message"] = "Submitted to Render Queue at %s" % base
        data["url"] = base
        return data
    except Exception as e:
        store = JobStore(config.queue_dir(settings))
        created = []
        for item in jobs:
            copy_from = None
            if isinstance(item, dict):
                copy_from = item.pop("copy_from", None)
                if copy_from and os.path.isfile(copy_from):
                    ext = os.path.splitext(copy_from)[1] or ".dat"
                    item["source_file"] = store.save_script_copy(
                        copy_from, item.get("app") or "job", ext)
            created.append(store.create(**item))
        return {
            "ok": True, "jobs": created, "mode": "folder", "url": base,
            "message": ("Queue server not reachable (%s). "
                        "Jobs written to %s — start the queue with: python -m paai_render_queue"
                        % (e, store.root)),
        }


def open_ui(base_url=None, settings=None, show_root=None, queue_path=None):
    import webbrowser
    url = discover_url(show_root=show_root, queue_path=queue_path, base_url=base_url).rstrip("/") + "/"
    webbrowser.open(url)
    return url


def ensure_import(queue_path: str = None):
    """Put paai_render_queue on sys.path from an install folder (no /workspace hardcode)."""
    candidates = []
    if queue_path:
        qp = os.path.abspath(os.path.expanduser(queue_path))
        candidates += [qp, os.path.dirname(qp)]
        # if user pointed at .../paai_render_queue, parent is needed
        if os.path.basename(qp.rstrip("/\\")) == "paai_render_queue":
            candidates.append(os.path.dirname(qp))
    # sibling of this file when packaged next to DCC packs
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.dirname(here))
    for c in candidates:
        if not c:
            continue
        if os.path.isdir(os.path.join(c, "paai_render_queue")) and c not in sys.path:
            sys.path.insert(0, c)
            return c
        if os.path.basename(c.rstrip("/\\")) == "paai_render_queue" and os.path.isfile(os.path.join(c, "__init__.py")):
            parent = os.path.dirname(c)
            if parent not in sys.path:
                sys.path.insert(0, parent)
            return parent
    return None
