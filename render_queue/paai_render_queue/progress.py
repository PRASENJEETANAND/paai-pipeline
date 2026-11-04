"""Parse progress from renderer stdout / ComfyUI API."""
from __future__ import annotations
import re

# Nuke: Frame 1001 (1 of 120)  or  Frame 1001 (10%)
NUKE_RE = re.compile(
    r"Frame\s+(\d+)\s*(?:\((\d+)\s+of\s+(\d+)\)|\((\d+(?:\.\d+)?)%\))?",
    re.I,
)
# Blender: Fra:12 Mem:...  or  Saved: '...'  Fra:12
BLENDER_RE = re.compile(r"\bFra:\s*(\d+)\b")
# Generic percent
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def parse_line(app: str, line: str, job: dict):
    """Update job['progress'] from a log line. Returns True if changed."""
    prog = job.setdefault("progress", {"frame": 0, "total": 0, "percent": 0.0, "message": ""})
    changed = False
    line = (line or "").rstrip()
    if not line:
        return False

    if app == "nuke":
        m = NUKE_RE.search(line)
        if m:
            frame = int(m.group(1))
            prog["frame"] = frame
            if m.group(2) and m.group(3):
                cur, total = int(m.group(2)), int(m.group(3))
                prog["total"] = total
                prog["percent"] = round(100.0 * cur / max(1, total), 2)
            elif m.group(4):
                prog["percent"] = float(m.group(4))
            else:
                fr = job.get("frames") or {}
                start, end, step = fr.get("start", 1), fr.get("end", 1), max(1, fr.get("step", 1))
                total = max(1, (end - start) // step + 1)
                cur = max(0, (frame - start) // step + 1)
                prog["total"] = total
                prog["percent"] = round(100.0 * cur / total, 2)
            prog["message"] = line[:200]
            changed = True
    elif app == "blender":
        m = BLENDER_RE.search(line)
        if m:
            frame = int(m.group(1))
            prog["frame"] = frame
            fr = job.get("frames") or {}
            start, end, step = fr.get("start", 1), fr.get("end", 1), max(1, fr.get("step", 1))
            total = max(1, (end - start) // step + 1)
            cur = max(0, (frame - start) // step + 1)
            prog["total"] = total
            prog["percent"] = round(min(100.0, 100.0 * cur / total), 2)
            prog["message"] = line[:200]
            changed = True
    elif app == "comfyui":
        m = PCT_RE.search(line)
        if m:
            prog["percent"] = float(m.group(1))
            prog["message"] = line[:200]
            changed = True

    return changed


def apply_comfy_history(job: dict, history_entry: dict):
    """Mark progress from a ComfyUI /history item."""
    prog = job.setdefault("progress", {"frame": 0, "total": 0, "percent": 0.0, "message": ""})
    status = (history_entry or {}).get("status") or {}
    if status.get("completed"):
        prog["percent"] = 100.0
        prog["message"] = "completed"
        return True
    if status.get("status_str"):
        prog["message"] = str(status.get("status_str"))[:200]
        return True
    return False
