"""Standalone PAAI Render Queue HTTP client (stdlib only).

Byte-identical copy lives in the Nuke, Blender and ComfyUI packs so submitters
do NOT need to import the paai_render_queue package.

Discovery order for the queue URL:
  1. explicit URL argument / field
  2. show-level render_queue_path (URL, or folder with queue_url.json)
  3. ~/.paai/render_queue_location.json (+ data_folder/queue_url.json it points to)
  4. <Documents>/PAAI Render Queue/queue_url.json
  5. http://127.0.0.1:8790
"""
from __future__ import print_function

import json
import os
import sys
import webbrowser

try:
    import urllib.error
    import urllib.request
except ImportError:  # pragma: no cover
    urllib = None  # type: ignore

DEFAULT_PORT = 8790
DEFAULT_URL = "http://127.0.0.1:%d" % DEFAULT_PORT
DATA_DIR_NAME = "PAAI Render Queue"
POINTER_DIR = os.path.join(os.path.expanduser("~"), ".paai")
POINTER_FILE = os.path.join(POINTER_DIR, "render_queue_location.json")
DISCOVERY_NAME = "queue_url.json"


# ------------------------------------------------------------------ paths / Documents

def _norm(p):
    if p is None:
        return ""
    p = str(p).strip().replace("\\", "/")
    return p


def _is_url(value):
    v = (value or "").strip().lower()
    return v.startswith("http://") or v.startswith("https://")


def documents_dir():
    """User Documents folder (Windows OneDrive / Known Folder aware)."""
    env = (os.environ.get("XDG_DOCUMENTS_DIR") or "").strip()
    if env:
        return os.path.expanduser(env)

    if sys.platform.startswith("win"):
        home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        # Registry: Shell Folders Personal (often OneDrive-redirected)
        try:
            import winreg  # type: ignore
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            )
            val, _ = winreg.QueryValueEx(key, "Personal")
            winreg.CloseKey(key)
            val = os.path.expandvars(val)
            if val and os.path.isdir(val):
                return val
        except Exception:
            pass
        for cand in (
            os.path.join(home, "Documents"),
            os.path.join(home, "OneDrive", "Documents"),
            os.path.join(home, "OneDrive - Personal", "Documents"),
        ):
            if os.path.isdir(cand):
                return cand
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", wintypes.BYTE * 8),
                ]

            fid = GUID(
                0xFDD39AD0, 0x238F, 0x46AF,
                (wintypes.BYTE * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
            )
            path_ptr = ctypes.c_wchar_p()
            ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(fid), 0, None, ctypes.byref(path_ptr)
            )
            if path_ptr.value:
                return path_ptr.value
        except Exception:
            pass
        return os.path.join(home, "Documents")

    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Documents")

    try:
        ud = os.path.join(os.path.expanduser("~"), ".config", "user-dirs.dirs")
        if os.path.isfile(ud):
            with open(ud) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("XDG_DOCUMENTS_DIR"):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        val = val.replace("$HOME", os.path.expanduser("~"))
                        return os.path.expanduser(val)
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def default_data_home():
    return os.path.join(documents_dir(), DATA_DIR_NAME)


def _read_json(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _url_from_payload(data):
    if not data:
        return ""
    url = (data.get("url") or data.get("queue_url") or "").strip()
    return url.rstrip("/") if url else ""


def _url_from_folder(folder):
    """Read queue_url.json from a folder (data home or user-supplied path)."""
    if not folder:
        return ""
    folder = os.path.abspath(os.path.expanduser(folder))
    if not os.path.isdir(folder):
        # maybe path is the json file itself
        if os.path.isfile(folder) and folder.lower().endswith(".json"):
            return _url_from_payload(_read_json(folder))
        return ""
    for name in (DISCOVERY_NAME, "render_queue_location.json"):
        url = _url_from_payload(_read_json(os.path.join(folder, name)))
        if url:
            return url
    # parent or nested paai_render_queue install folder — still look for discovery beside it
    nested = os.path.join(folder, DATA_DIR_NAME)
    if os.path.isdir(nested):
        url = _url_from_payload(_read_json(os.path.join(nested, DISCOVERY_NAME)))
        if url:
            return url
    return ""


# ------------------------------------------------------------------ discovery

def discover_url(explicit_url=None, queue_path=None, show_root=None):
    """Resolve the running queue base URL (no trailing slash)."""
    if explicit_url and _is_url(explicit_url):
        return explicit_url.strip().rstrip("/")

    # queue_path may itself be a URL (Render Queue path field accepts either)
    if queue_path and _is_url(queue_path):
        return queue_path.strip().rstrip("/")

    if queue_path:
        url = _url_from_folder(queue_path)
        if url:
            return url

    # show_root alone does not hold the URL; callers pass render_queue_path via queue_path.
    # Still accept show_root/showset/config hint files if present.
    if show_root:
        try:
            cfg_path = os.path.join(
                os.path.expanduser(show_root), "showset", "config", "show_config.txt"
            )
            if os.path.isfile(cfg_path):
                with open(cfg_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("render_queue_path") and "=" in line:
                            val = line.split("=", 1)[1].strip()
                            if _is_url(val):
                                return val.rstrip("/")
                            url = _url_from_folder(val)
                            if url:
                                return url
        except Exception:
            pass

    # ~/.paai/render_queue_location.json
    ptr = _read_json(POINTER_FILE)
    url = _url_from_payload(ptr)
    if url:
        return url
    pointed = (ptr.get("data_folder") or ptr.get("path") or "").strip()
    if pointed:
        url = _url_from_folder(pointed)
        if url:
            return url

    # Default Documents home
    url = _url_from_folder(default_data_home())
    if url:
        return url

    return DEFAULT_URL


def not_running_message(url=None):
    url = (url or DEFAULT_URL).rstrip("/")
    return (
        "PAAI Render Queue not running at %s, start it with run_queue.bat "
        "(or: python -m paai_render_queue)"
    ) % url


# ------------------------------------------------------------------ HTTP helpers

def _request(method, url, body=None, timeout=5.0):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def ping(url=None, queue_path=None, show_root=None, base_url=None, timeout=1.5):
    base = discover_url(explicit_url=url or base_url, queue_path=queue_path, show_root=show_root)
    try:
        data = _request("GET", base + "/api/ping", timeout=timeout)
        data = data or {}
        data.setdefault("ok", True)
        data["url"] = base
        return data
    except Exception as e:
        return {
            "ok": False,
            "url": base,
            "error": str(e),
            "message": not_running_message(base),
        }


def health(url=None, queue_path=None, show_root=None, timeout=1.5):
    """Alias for ping."""
    return ping(url=url, queue_path=queue_path, show_root=show_root, timeout=timeout)


def list_jobs(url=None, queue_path=None, show_root=None, timeout=5.0):
    base = discover_url(explicit_url=url, queue_path=queue_path, show_root=show_root)
    try:
        data = _request("GET", base + "/api/jobs", timeout=timeout)
        data = data or {}
        data["ok"] = True
        data["url"] = base
        return data
    except Exception as e:
        return {
            "ok": False,
            "url": base,
            "jobs": [],
            "error": str(e),
            "message": not_running_message(base),
        }


def submit_jobs(jobs, url=None, queue_path=None, show_root=None, timeout=8.0):
    """POST jobs to the live queue. No silent folder fallback.

    jobs: dict or list of dicts matching the queue schema (nested resources preferred).
    Returns {ok, jobs, url, message, error?}.
    """
    if isinstance(jobs, dict):
        jobs = [jobs]
    base = discover_url(explicit_url=url, queue_path=queue_path, show_root=show_root)
    # Soft-check first so the error message is clear
    pre = ping(url=base, timeout=1.5)
    if not pre.get("ok"):
        msg = not_running_message(base)
        return {"ok": False, "jobs": [], "url": base, "message": msg, "error": pre.get("error") or msg}
    try:
        data = _request("POST", base + "/api/jobs", body={"jobs": jobs}, timeout=timeout)
        data = data or {}
        data["ok"] = True if data.get("ok", True) else False
        data["url"] = base
        data.setdefault(
            "message",
            "Submitted %d job(s) to Render Queue at %s" % (len(data.get("jobs") or jobs), base),
        )
        return data
    except Exception as e:
        msg = not_running_message(base)
        return {"ok": False, "jobs": [], "url": base, "message": msg, "error": str(e)}


# Back-compat aliases matching old client.submit / client.open_ui names
def submit(jobs, base_url=None, queue_path=None, show_root=None, url=None, **_kwargs):
    # Accept both base_url= (legacy client) and url=
    return submit_jobs(
        jobs,
        url=base_url or url or _kwargs.get("explicit_url"),
        queue_path=queue_path,
        show_root=show_root,
    )


def open_ui(base_url=None, queue_path=None, show_root=None, url=None, **_kwargs):
    resolved = discover_url(
        explicit_url=base_url or url,
        queue_path=queue_path,
        show_root=show_root,
    )
    webbrowser.open(resolved.rstrip("/") + "/")
    return resolved
