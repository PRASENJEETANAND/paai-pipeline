"""JSON file job store under the queue folder."""
from __future__ import annotations
import json
import os
import shutil
import threading
import time
from . import models

_lock = threading.RLock()


class JobStore:
    def __init__(self, queue_folder: str):
        self.root = queue_folder
        self.jobs_dir = os.path.join(queue_folder, "jobs")
        self.scripts_dir = os.path.join(queue_folder, "scripts")
        self.logs_dir = os.path.join(queue_folder, "logs")
        for d in (self.jobs_dir, self.scripts_dir, self.logs_dir):
            os.makedirs(d, exist_ok=True)

    def _path(self, job_id: str) -> str:
        return os.path.join(self.jobs_dir, job_id + ".json")

    def list_jobs(self):
        with _lock:
            out = []
            for name in sorted(os.listdir(self.jobs_dir)):
                if not name.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(self.jobs_dir, name)) as f:
                        out.append(json.load(f))
                except Exception:
                    continue
            # priority desc, created asc
            out.sort(key=lambda j: (-int(j.get("priority", 50)),
                                    float((j.get("times") or {}).get("created") or 0)))
            return out

    def get(self, job_id: str):
        path = self._path(job_id)
        with _lock:
            if not os.path.isfile(path):
                return None
            with open(path) as f:
                return json.load(f)

    def save(self, job: dict):
        with _lock:
            job = models.touch(job)
            path = self._path(job["id"])
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(job, f, indent=2)
            os.replace(tmp, path)
        return job

    def delete(self, job_id: str, remove_files=False):
        with _lock:
            job = self.get(job_id)
            path = self._path(job_id)
            if os.path.isfile(path):
                os.remove(path)
            if remove_files and job:
                for k in ("log_path", "source_file"):
                    p = job.get(k) or ""
                    if p and os.path.isfile(p) and p.startswith(self.root):
                        try:
                            os.remove(p)
                        except Exception:
                            pass
            return job

    def create(self, **kwargs):
        job = models.new_job(**kwargs)
        if not job.get("log_path"):
            job["log_path"] = os.path.join(self.logs_dir, job["id"] + ".log")
        return self.save(job)

    def update(self, job_id: str, **fields):
        with _lock:
            job = self.get(job_id)
            if not job:
                return None
            job.update(fields)
            return self.save(job)

    def save_script_copy(self, src_path: str, prefix: str, ext: str) -> str:
        """Copy a source file into scripts/ with a timestamped name."""
        os.makedirs(self.scripts_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = os.path.splitext(os.path.basename(src_path or "untitled"))[0] or "untitled"
        dest = os.path.join(self.scripts_dir, "%s_%s_%s%s" % (prefix, base, stamp, ext))
        if src_path and os.path.isfile(src_path):
            shutil.copy2(src_path, dest)
        return dest
