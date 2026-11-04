"""PAAI Render Queue settings — user data folder (not tied to any show).

Default data home:  <Documents>/PAAI Render Queue/
Pointer file:       ~/.paai/render_queue_location.json  (or env PAAI_RQ_HOME)
Settings file:      <data_home>/settings.json
Jobs / logs / scripts live under <data_home>/.
"""
from __future__ import annotations
import json
import os
import sys
import multiprocessing
from copy import deepcopy

DEFAULT_PORT = 8790
DEFAULT_HOST = "127.0.0.1"
DATA_DIR_NAME = "PAAI Render Queue"
POINTER_DIR = os.path.join(os.path.expanduser("~"), ".paai")
POINTER_FILE = os.path.join(POINTER_DIR, "render_queue_location.json")

_DEFAULTS = {
    "data_folder": "",           # blank -> resolve_default_data_home()
    "port": DEFAULT_PORT,
    "comfyui_servers": [
        {"name": "local", "url": "http://127.0.0.1:8188"},
    ],
    "nuke_launcher": "",
    "blender_launcher": "",
    "total_cpu_cores": 0,
    "max_concurrent_jobs": 2,
    "gpus": [],
    "auto_start": False,  # manual Start by default
}


def auto_cores():
    try:
        return multiprocessing.cpu_count() or 4
    except Exception:
        return 4


def default_settings():
    d = deepcopy(_DEFAULTS)
    d["total_cpu_cores"] = auto_cores()
    return d


# ------------------------------------------------------------------ Documents / data home

def documents_dir() -> str:
    """Resolve the user's Documents folder across Windows / macOS / Linux."""
    # Explicit override
    env = (os.environ.get("XDG_DOCUMENTS_DIR") or "").strip()
    if env:
        return os.path.expanduser(env)

    if sys.platform.startswith("win"):
        home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        # Registry User Shell Folders\Personal (OneDrive-redirected Documents)
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
            fid = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                       (wintypes.BYTE * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            path_ptr = ctypes.c_wchar_p()
            ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(fid), 0, None, ctypes.byref(path_ptr))
            if path_ptr.value:
                return path_ptr.value
        except Exception:
            pass
        return os.path.join(home, "Documents")

    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Documents")

    # Linux: ~/.config/user-dirs.dirs
    try:
        ud = os.path.join(os.path.expanduser("~"), ".config", "user-dirs.dirs")
        if os.path.isfile(ud):
            with open(ud) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("XDG_DOCUMENTS_DIR"):
                        # XDG_DOCUMENTS_DIR="$HOME/Documents"
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        val = val.replace("$HOME", os.path.expanduser("~"))
                        return os.path.expanduser(val)
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def resolve_default_data_home() -> str:
    return os.path.join(documents_dir(), DATA_DIR_NAME)


def read_pointer() -> str:
    """Return data folder from env or pointer file, else ''."""
    env = (os.environ.get("PAAI_RQ_HOME") or "").strip()
    if env:
        return os.path.expanduser(env)
    try:
        with open(POINTER_FILE) as f:
            data = json.load(f)
        return (data.get("data_folder") or data.get("path") or "").strip()
    except Exception:
        return ""


def write_pointer(data_folder: str) -> str:
    os.makedirs(POINTER_DIR, exist_ok=True)
    path = os.path.abspath(os.path.expanduser(data_folder))
    with open(POINTER_FILE, "w") as f:
        json.dump({"data_folder": path}, f, indent=2)
    return path


def data_home(settings: dict = None) -> str:
    """Resolved absolute data folder (creates it)."""
    if settings:
        explicit = (settings.get("data_folder") or "").strip()
        if explicit:
            home = os.path.abspath(os.path.expanduser(explicit))
            os.makedirs(home, exist_ok=True)
            return home
    pointed = read_pointer()
    if pointed:
        home = os.path.abspath(os.path.expanduser(pointed))
        os.makedirs(home, exist_ok=True)
        return home
    home = resolve_default_data_home()
    os.makedirs(home, exist_ok=True)
    # seed pointer so submitters find us
    try:
        write_pointer(home)
    except Exception:
        pass
    return home


def settings_path(home: str = None) -> str:
    home = home or data_home()
    return os.path.join(home, "settings.json")


def queue_dir(settings: dict = None) -> str:
    """Jobs live directly under the data home (jobs/, scripts/, logs/)."""
    return data_home(settings)


# ------------------------------------------------------------------ load / save

def load_settings(_ignored_root: str = "") -> dict:
    """Load settings from the user data folder. Argument kept for call-site compat (ignored)."""
    settings = default_settings()
    home = data_home()  # resolves pointer / default, creates dir
    settings["data_folder"] = home
    path = settings_path(home)
    if os.path.isfile(path):
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                # Migration: drop obsolete keys (showset_root / queue_folder from early builds).
                data.pop("showset_root", None)
                data.pop("queue_folder", None)
                settings.update({k: v for k, v in data.items() if v is not None})
        except Exception:
            pass
    settings["data_folder"] = home  # always reflect resolved home
    if not settings.get("total_cpu_cores"):
        settings["total_cpu_cores"] = auto_cores()
    return settings


def save_settings(settings: dict) -> str:
    """Save settings into data_folder/settings.json and update the pointer."""
    home = (settings.get("data_folder") or "").strip() or data_home(settings)
    home = os.path.abspath(os.path.expanduser(home))
    os.makedirs(home, exist_ok=True)
    settings = deepcopy(settings)
    settings["data_folder"] = home
    # Migration: strip obsolete keys (safe to keep popping indefinitely).
    settings.pop("showset_root", None)
    settings.pop("queue_folder", None)
    path = settings_path(home)
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)
    try:
        write_pointer(home)
    except Exception:
        pass
    return path


def move_data(old_home: str, new_home: str) -> dict:
    """Move jobs/scripts/logs/settings to a new data folder. Returns summary."""
    import shutil
    old_home = os.path.abspath(os.path.expanduser(old_home or ""))
    new_home = os.path.abspath(os.path.expanduser(new_home or ""))
    if not old_home or not new_home or old_home == new_home:
        return {"ok": False, "error": "same or empty path"}
    os.makedirs(new_home, exist_ok=True)
    moved = []
    for name in ("jobs", "scripts", "logs", "settings.json"):
        src = os.path.join(old_home, name)
        dst = os.path.join(new_home, name)
        if not os.path.exists(src):
            continue
        if os.path.exists(dst):
            # merge: if dir, copy missing; if file, keep existing dst
            if os.path.isdir(src) and os.path.isdir(dst):
                for root, dirs, files in os.walk(src):
                    rel = os.path.relpath(root, src)
                    target_root = dst if rel == "." else os.path.join(dst, rel)
                    os.makedirs(target_root, exist_ok=True)
                    for fn in files:
                        s, d = os.path.join(root, fn), os.path.join(target_root, fn)
                        if not os.path.exists(d):
                            shutil.copy2(s, d)
                moved.append(name + " (merged)")
            else:
                moved.append(name + " (skipped, exists)")
        else:
            shutil.move(src, dst)
            moved.append(name)
    write_pointer(new_home)
    return {"ok": True, "old": old_home, "new": new_home, "moved": moved}


# Back-compat aliases used by older call sites
def config_path(root: str = "") -> str:
    return settings_path()


# ------------------------------------------------------------------ live server discovery

def discovery_path(home: str = None) -> str:
    home = home or data_home()
    return os.path.join(home, "queue_url.json")


def write_discovery(url: str, port: int, home: str = None) -> str:
    """Write live queue URL into data home and ~/.paai/render_queue_location.json."""
    home = home or data_home()
    os.makedirs(home, exist_ok=True)
    payload = {
        "url": url,
        "port": int(port),
        "data_folder": os.path.abspath(home),
        "host": "127.0.0.1",
    }
    path = discovery_path(home)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    # merge into pointer file
    try:
        os.makedirs(POINTER_DIR, exist_ok=True)
        data = {}
        if os.path.isfile(POINTER_FILE):
            try:
                with open(POINTER_FILE) as f:
                    data = json.load(f) or {}
            except Exception:
                data = {}
        data.update({"data_folder": os.path.abspath(home), "url": url, "port": int(port)})
        with open(POINTER_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass
    return path


def read_discovery(extra_homes=None) -> dict:
    """Find a running-queue discovery record. Returns dict with url/port/data_folder or {}."""
    homes = []
    for h in (extra_homes or []):
        if h:
            homes.append(os.path.abspath(os.path.expanduser(h)))
    pointed = read_pointer()
    if pointed:
        homes.append(os.path.abspath(os.path.expanduser(pointed)))
    try:
        homes.append(resolve_default_data_home())
    except Exception:
        pass
    # pointer file itself may carry url
    try:
        with open(POINTER_FILE) as f:
            data = json.load(f) or {}
        if data.get("url"):
            return data
    except Exception:
        pass
    seen = set()
    for home in homes:
        if not home or home in seen:
            continue
        seen.add(home)
        path = os.path.join(home, "queue_url.json")
        try:
            with open(path) as f:
                data = json.load(f) or {}
            if data.get("url"):
                return data
        except Exception:
            continue
    return {}


def pick_free_port(preferred: int = None, host: str = "127.0.0.1") -> int:
    import socket
    preferred = int(preferred or DEFAULT_PORT)
    # try preferred first
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, preferred))
        s.close()
        return preferred
    except OSError:
        try:
            s.close()
        except Exception:
            pass
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, 0))
    port = s.getsockname()[1]
    s.close()
    return int(port)
