"""Parallel job scheduler with manual Start, Auto start, and per-job controls."""
from __future__ import annotations
import os
import signal
import sys
import threading
import time

from . import executors
from . import progress

# Queue-wide states
STATE_STOPPED = "stopped"
STATE_RUNNING = "running"
STATE_PAUSED = "paused"

# Job statuses that the dispatcher may pick up when the queue is running
# 'ready' = user pressed Start on this job while queue was stopped — always eligible
DISPATCHABLE = ("queued", "ready", "waiting")


class Scheduler:
    def __init__(self, store, settings: dict):
        self.store = store
        self.settings = settings
        self._lock = threading.RLock()
        self._handles = {}          # job_id -> handle dict
        self._reserved_cpu = {}
        self._reserved_gpu = {}
        self._queue_state = STATE_STOPPED  # default: manual start
        self._stop = threading.Event()
        self._thread = None
        self._recover_orphans()

    # ------------------------------------------------------------------ lifecycle

    def update_settings(self, settings: dict):
        with self._lock:
            self.settings = settings
            # auto_start does not flip queue_state by itself; Start button / auto does

    def start(self):
        """Start the background tick thread (always running so per-job Start works)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        with self._lock:
            ids = list(self._handles.keys())
        for jid in ids:
            self.kill_job(jid)

    def _recover_orphans(self):
        """On startup, mark leftover 'running' jobs as failed/interrupted."""
        for job in self.store.list_jobs():
            if job.get("status") in ("running",):
                job["status"] = "failed"
                job["error"] = "interrupted: queue server restarted"
                job["pid"] = None
                job["wait_reason"] = ""
                job.setdefault("times", {})["finished"] = time.time()
                self.store.save(job)
            elif job.get("status") == "waiting":
                # re-evaluate next tick
                job["status"] = "queued"
                job["wait_reason"] = ""
                self.store.save(job)

    # ------------------------------------------------------------------ queue controls

    def start_queue(self):
        """Begin dispatching queued/ready/waiting jobs (respects resources)."""
        self._queue_state = STATE_RUNNING
        return self.status()

    def pause_queue(self, paused=True):
        if paused:
            self._queue_state = STATE_PAUSED
            # also suspend all running processes
            with self._lock:
                ids = list(self._handles.keys())
            for jid in ids:
                self._suspend_handle(jid)
                job = self.store.get(jid)
                if job and job.get("status") == "running":
                    job["status"] = "paused"
                    self.store.save(job)
        else:
            # resume queue dispatch; also resume suspended procs that were queue-paused
            self._queue_state = STATE_RUNNING
            for job in self.store.list_jobs():
                if job.get("status") == "paused" and job.get("id") in self._handles:
                    self._resume_handle(job["id"])
                    job["status"] = "running"
                    self.store.save(job)
        return self.status()

    def stop_queue(self):
        """Stop dispatching new jobs; leave running jobs alone."""
        self._queue_state = STATE_STOPPED
        return self.status()

    @property
    def auto_start(self):
        return bool(self.settings.get("auto_start", False))

    def status(self):
        with self._lock:
            used = sum(self._reserved_cpu.values())
            total = int(self.settings.get("total_cpu_cores") or 0)
            return {
                "state": self._queue_state,
                "auto_start": self.auto_start,
                "paused": self._queue_state == STATE_PAUSED,
                "running": list(self._handles.keys()),
                "reserved_cpu": used,
                "reserved_gpu": list(self._reserved_gpu.values()),
                "total_cpu": total,
                "max_concurrent": int(self.settings.get("max_concurrent_jobs") or 1),
                "gpus": list(self.settings.get("gpus") or []),
            }

    # ------------------------------------------------------------------ tick

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                print("[PAAI RQ] scheduler:", e)
            self._stop.wait(0.4)

    def _tick(self):
        self._reap_finished()
        if self._queue_state == STATE_PAUSED:
            return
        # When stopped: only dispatch jobs explicitly marked 'ready'
        # When running: dispatch queued/ready/waiting (auto or after Start)
        allow_queued = self._queue_state == STATE_RUNNING
        # keep trying to backfill
        while True:
            job = self._pick_next(allow_queued=allow_queued)
            if not job:
                break
            reason = self._resource_block_reason(job)
            if reason:
                if job.get("status") != "waiting" or job.get("wait_reason") != reason:
                    job["status"] = "waiting"
                    job["wait_reason"] = reason
                    self.store.save(job)
                # try a smaller/later job that might fit (backfill)
                fitted = self._pick_backfill(exclude_id=job["id"], allow_queued=allow_queued)
                if not fitted:
                    break
                job = fitted
                reason = self._resource_block_reason(job)
                if reason:
                    break
            self._start_job(job)

    def _reap_finished(self):
        with self._lock:
            finished = []
            for jid, handle in list(self._handles.items()):
                proc = handle.get("proc")
                if proc is None:
                    continue
                code = proc.poll()
                if code is None:
                    continue
                finished.append((jid, code, handle))
            for jid, code, handle in finished:
                self._release(jid)
                self._handles.pop(jid, None)
                job = self.store.get(jid)
                if not job:
                    continue
                if job.get("status") in ("killed", "cancelled"):
                    continue
                job["pid"] = None
                job["wait_reason"] = ""
                job.setdefault("times", {})["finished"] = time.time()
                if code == 0:
                    job["status"] = "done"
                    job.setdefault("progress", {})["percent"] = 100.0
                    job["progress"]["message"] = "done"
                    job["error"] = ""
                else:
                    # Fail and continue — never block the queue
                    job["status"] = "failed"
                    job["error"] = "exit code %s" % code
                self.store.save(job)

    def _eligible(self, job, allow_queued):
        st = job.get("status")
        if st == "ready":
            return True
        if allow_queued and st in ("queued", "waiting"):
            return True
        return False

    def _pick_next(self, allow_queued=True):
        """Highest priority, then oldest created among dispatchable jobs."""
        jobs = self.store.list_jobs()  # already priority desc, created asc
        for j in jobs:
            if self._eligible(j, allow_queued):
                return j
        return None

    def _pick_backfill(self, exclude_id, allow_queued=True):
        """Find a job that fits remaining resources (smaller backfill)."""
        for j in self.store.list_jobs():
            if j.get("id") == exclude_id:
                continue
            if not self._eligible(j, allow_queued):
                continue
            if not self._resource_block_reason(j):
                return j
        return None

    def _resource_block_reason(self, job):
        with self._lock:
            running = len(self._handles)
            max_c = int(self.settings.get("max_concurrent_jobs") or 1)
            if running >= max_c:
                return "waiting: max concurrent %d/%d" % (running, max_c)
            total = int(self.settings.get("total_cpu_cores") or 0)
            need = int((job.get("resources") or {}).get("cpu_cores") or 1)
            used = sum(self._reserved_cpu.values())
            if total and used + need > total:
                return "waiting: CPU %d/%d used (need %d)" % (used, total, need)
            gpu = (job.get("resources") or {}).get("gpu_index")
            gpus = list(self.settings.get("gpus") or [])
            if gpu is not None and gpu != "" and gpus:
                try:
                    gpu = int(gpu)
                except Exception:
                    return "waiting: invalid GPU"
                if gpu not in gpus:
                    return "waiting: GPU %s not in pool" % gpu
                if gpu in self._reserved_gpu.values():
                    return "waiting: GPU %s busy" % gpu
            return ""

    def _start_job(self, job):
        jid = job["id"]
        # guard double-start
        with self._lock:
            if jid in self._handles:
                return
        need = int((job.get("resources") or {}).get("cpu_cores") or 1)
        gpu = (job.get("resources") or {}).get("gpu_index")
        if gpu == "":
            gpu = None
        if gpu is not None:
            try:
                gpu = int(gpu)
            except Exception:
                gpu = None

        def on_line(line):
            j = self.store.get(jid)
            if not j:
                return
            if progress.parse_line(j.get("app"), line, j):
                self.store.save(j)

        try:
            ex = executors.get_executor(job.get("app"), self.settings)
            handle = ex.start(job, on_line=on_line)
        except Exception as e:
            job["status"] = "failed"
            job["error"] = "start failed: %s" % e
            job.setdefault("times", {})["finished"] = time.time()
            self.store.save(job)
            return

        with self._lock:
            self._handles[jid] = {"executor": ex, **handle}
            self._reserved_cpu[jid] = need
            if gpu is not None:
                self._reserved_gpu[jid] = gpu
        job["status"] = "running"
        job["wait_reason"] = ""
        job["pid"] = getattr(handle.get("proc"), "pid", None)
        job.setdefault("times", {})["started"] = time.time()
        job["times"]["finished"] = None
        job["error"] = ""
        self.store.save(job)

    def _release(self, jid):
        with self._lock:
            self._reserved_cpu.pop(jid, None)
            self._reserved_gpu.pop(jid, None)

    # ------------------------------------------------------------------ per-job

    def start_job(self, job_id: str):
        """Start this job now if resources free; else mark ready (runs ASAP even if queue stopped)."""
        job = self.store.get(job_id)
        if not job:
            return None
        if job.get("status") == "running":
            return job
        if job.get("status") == "paused" and job_id in self._handles:
            return self.resume_job(job_id)
        # mark ready so dispatcher picks it even when queue is stopped
        job["status"] = "ready"
        job["wait_reason"] = ""
        job["error"] = ""
        self.store.save(job)
        # try immediate start
        if not self._resource_block_reason(job):
            self._start_job(job)
            return self.store.get(job_id)
        job["status"] = "waiting"
        job["wait_reason"] = self._resource_block_reason(job) or "waiting: resources"
        # keep as ready+waiting: use 'ready' so stopped queue still considers it
        job["status"] = "ready"
        self.store.save(job)
        return job

    def pause_job(self, job_id: str):
        job = self.store.get(job_id)
        if not job:
            return None
        st = job.get("status")
        if st in ("queued", "waiting", "ready"):
            job["status"] = "paused"
            job["wait_reason"] = "held"
            return self.store.save(job)
        if st == "running":
            ok = self._suspend_handle(job_id)
            job["status"] = "paused"
            job["wait_reason"] = ""
            if not ok:
                # fallback: if suspend unsupported, leave note but keep handle
                job["error"] = job.get("error") or ""
            return self.store.save(job)
        return job

    def resume_job(self, job_id: str):
        job = self.store.get(job_id)
        if not job:
            return None
        if job.get("status") != "paused":
            return job
        if job_id in self._handles:
            self._resume_handle(job_id)
            job["status"] = "running"
            job["wait_reason"] = ""
            return self.store.save(job)
        # was held while queued
        job["status"] = "ready" if self._queue_state == STATE_STOPPED else "queued"
        job["wait_reason"] = ""
        job["error"] = ""
        return self.store.save(job)

    def kill_job(self, job_id: str):
        with self._lock:
            handle = self._handles.get(job_id)
        if handle:
            ex = handle.get("executor")
            if ex:
                ex.cancel(handle)
            else:
                executors.kill_tree(getattr(handle.get("proc"), "pid", None))
        job = self.store.get(job_id)
        if job:
            job["status"] = "killed"
            job["wait_reason"] = ""
            job["error"] = "killed by user"
            job["pid"] = None
            job.setdefault("times", {})["finished"] = time.time()
            self.store.save(job)
        with self._lock:
            self._handles.pop(job_id, None)
            self._release(job_id)
        return job

    # keep old name as alias
    def cancel_job(self, job_id: str):
        return self.kill_job(job_id)

    def retry_job(self, job_id: str):
        job = self.store.get(job_id)
        if not job:
            return None
        if job.get("status") in ("failed", "cancelled", "killed", "done", "paused"):
            # drop any lingering handle
            with self._lock:
                if job_id in self._handles:
                    self.kill_job(job_id)
                    job = self.store.get(job_id)
            job["status"] = "ready" if (self._queue_state == STATE_STOPPED and not self.auto_start) else "queued"
            if self.auto_start and self._queue_state != STATE_PAUSED:
                job["status"] = "queued"
                if self._queue_state == STATE_STOPPED:
                    self._queue_state = STATE_RUNNING
            job["error"] = ""
            job["pid"] = None
            job["wait_reason"] = ""
            job["progress"] = {"frame": 0, "total": job.get("progress", {}).get("total", 0),
                               "percent": 0.0, "message": "retry"}
            job.setdefault("times", {})["started"] = None
            job["times"]["finished"] = None
            return self.store.save(job)
        return job

    # ------------------------------------------------------------------ process suspend

    def _suspend_handle(self, job_id):
        with self._lock:
            handle = self._handles.get(job_id)
        if not handle:
            return False
        # ComfyUI: set a pause flag on handle state
        state = handle.get("state")
        if state is not None:
            state["paused"] = True
            return True
        proc = handle.get("proc")
        pid = getattr(proc, "pid", None)
        if not pid:
            return False
        try:
            if sys.platform.startswith("win"):
                return _win_suspend(pid)
            os.kill(pid, signal.SIGSTOP)
            # also stop children via process group if we used setsid
            try:
                os.killpg(pid, signal.SIGSTOP)
            except Exception:
                pass
            return True
        except Exception as e:
            print("[PAAI RQ] suspend:", e)
            return False

    def _resume_handle(self, job_id):
        with self._lock:
            handle = self._handles.get(job_id)
        if not handle:
            return False
        state = handle.get("state")
        if state is not None:
            state["paused"] = False
            return True
        proc = handle.get("proc")
        pid = getattr(proc, "pid", None)
        if not pid:
            return False
        try:
            if sys.platform.startswith("win"):
                return _win_resume(pid)
            try:
                os.killpg(pid, signal.SIGCONT)
            except Exception:
                os.kill(pid, signal.SIGCONT)
            return True
        except Exception as e:
            print("[PAAI RQ] resume:", e)
            return False


def _win_process_tree_pids(root_pid):
    """Return [root_pid, ...descendants] on Windows."""
    pids = [int(root_pid)]
    try:
        import psutil
        root = psutil.Process(int(root_pid))
        for c in root.children(recursive=True):
            pids.append(c.pid)
        return pids
    except Exception:
        pass
    # Toolhelp32 snapshot fallback
    try:
        import ctypes
        from ctypes import wintypes
        TH32CS_SNAPPROCESS = 0x00000002
        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260),
            ]
        kernel32 = ctypes.windll.kernel32
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == -1:
            return pids
        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
        children = {}
        ok = kernel32.Process32First(snap, ctypes.byref(pe))
        while ok:
            children.setdefault(int(pe.th32ParentProcessID), []).append(int(pe.th32ProcessID))
            ok = kernel32.Process32Next(snap, ctypes.byref(pe))
        kernel32.CloseHandle(snap)
        stack = [int(root_pid)]
        seen = set()
        out = []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            out.append(cur)
            stack.extend(children.get(cur, []))
        return out or pids
    except Exception:
        return pids


def _win_suspend(pid):
    try:
        import ctypes
        PROCESS_SUSPEND_RESUME = 0x0800
        kernel32 = ctypes.windll.kernel32
        ntdll = ctypes.windll.ntdll
        ok_any = False
        for child in _win_process_tree_pids(pid):
            handle = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, int(child))
            if not handle:
                continue
            try:
                ntdll.NtSuspendProcess(handle)
                ok_any = True
            finally:
                kernel32.CloseHandle(handle)
        return ok_any
    except Exception:
        return False


def _win_resume(pid):
    try:
        import ctypes
        PROCESS_SUSPEND_RESUME = 0x0800
        kernel32 = ctypes.windll.kernel32
        ntdll = ctypes.windll.ntdll
        ok_any = False
        # resume children first then root (reverse)
        tree = list(reversed(_win_process_tree_pids(pid)))
        for child in tree:
            handle = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, int(child))
            if not handle:
                continue
            try:
                ntdll.NtResumeProcess(handle)
                ok_any = True
            finally:
                kernel32.CloseHandle(handle)
        return ok_any
    except Exception:
        return False
