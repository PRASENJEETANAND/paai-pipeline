"""Job model helpers."""
from __future__ import annotations
import uuid
import getpass
import socket
import time
from copy import deepcopy

STATUSES = ("queued", "ready", "waiting", "running", "paused", "done", "failed", "cancelled", "killed")
APPS = ("nuke", "comfyui", "blender")


def new_job(**kwargs):
    now = time.time()
    job = {
        "id": kwargs.get("id") or ("rq_" + uuid.uuid4().hex[:12]),
        "app": kwargs.get("app") or "blender",
        "name": kwargs.get("name") or "untitled",
        "source_file": kwargs.get("source_file") or "",
        "target": kwargs.get("target") or "",          # Write name / view layer / workflow id
        "frames": {
            "start": int(kwargs.get("frame_start", kwargs.get("frames", {}).get("start", 1)
                         if isinstance(kwargs.get("frames"), dict) else 1)),
            "end": int(kwargs.get("frame_end", kwargs.get("frames", {}).get("end", 1)
                       if isinstance(kwargs.get("frames"), dict) else 1)),
            "step": int(kwargs.get("frame_step", kwargs.get("frames", {}).get("step", 1)
                        if isinstance(kwargs.get("frames"), dict) else 1)),
        },
        "repeats": int(kwargs.get("repeats", 1)),
        "resources": {
            "cpu_cores": int(kwargs.get("cpu_cores",
                             kwargs.get("resources", {}).get("cpu_cores", 1)
                             if isinstance(kwargs.get("resources"), dict) else 1)),
            "gpu_index": kwargs.get("gpu_index",
                          kwargs.get("resources", {}).get("gpu_index", None)
                          if isinstance(kwargs.get("resources"), dict) else None),
        },
        "priority": int(kwargs.get("priority", 50)),   # higher = sooner
        "status": "queued",
        "progress": {"frame": 0, "total": 0, "percent": 0.0, "message": ""},
        "log_path": kwargs.get("log_path") or "",
        "times": {"created": now, "started": None, "finished": None, "updated": now},
        "output_path": kwargs.get("output_path") or "",
        "user": kwargs.get("user") or _user(),
        "machine": kwargs.get("machine") or socket.gethostname(),
        "error": "",
        "wait_reason": "",
        "pid": None,
        "extra": kwargs.get("extra") or {},             # app-specific (comfy server, scene, etc.)
    }
    # normalize frames dict if passed whole
    if isinstance(kwargs.get("frames"), dict):
        job["frames"].update({k: int(v) for k, v in kwargs["frames"].items() if k in ("start", "end", "step")})
    if isinstance(kwargs.get("resources"), dict):
        job["resources"].update(kwargs["resources"])
    fr = job["frames"]
    total = max(0, (fr["end"] - fr["start"]) // max(1, fr["step"]) + 1) * max(1, job["repeats"])
    job["progress"]["total"] = total
    return job


def _user():
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def touch(job, **fields):
    j = deepcopy(job)
    j.update(fields)
    j.setdefault("times", {})["updated"] = time.time()
    return j
