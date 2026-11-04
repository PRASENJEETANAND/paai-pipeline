"""Launch Nuke / Blender / ComfyUI jobs and stream logs."""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from . import progress


def _which(cmd: str) -> str:
    if not cmd:
        return ""
    if os.path.isfile(cmd):
        return cmd
    from shutil import which
    return which(cmd) or cmd


def kill_tree(pid: int):
    if not pid:
        return
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            try:
                os.killpg(pid, signal.SIGTERM)
            except Exception:
                os.kill(pid, signal.SIGTERM)
            time.sleep(0.4)
            try:
                os.killpg(pid, signal.SIGKILL)
            except Exception:
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
    except Exception:
        pass


class BaseExecutor:
    app = "base"

    def __init__(self, settings: dict):
        self.settings = settings

    def build_cmd(self, job: dict):
        raise NotImplementedError

    def start(self, job: dict, on_line=None):
        """Start process; return dict with proc, thread, stop_event."""
        cmd = self.build_cmd(job)
        log_path = job.get("log_path") or os.devnull
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        logf = open(log_path, "a", buffering=1)
        logf.write("\n===== START %s =====\n$ %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(map(str, cmd))))
        logf.flush()
        env = os.environ.copy()
        gpu = (job.get("resources") or {}).get("gpu_index")
        if gpu is not None and gpu != "" and gpu != -1:
            env["CUDA_VISIBLE_DEVICES"] = str(gpu)
            env["HIP_VISIBLE_DEVICES"] = str(gpu)
        popen_kwargs = dict(
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, bufsize=1, universal_newlines=True,
        )
        if not sys.platform.startswith("win"):
            popen_kwargs["preexec_fn"] = os.setsid
        proc = subprocess.Popen(cmd, **popen_kwargs)
        stop = threading.Event()

        def reader():
            try:
                for line in proc.stdout:
                    logf.write(line)
                    logf.flush()
                    if on_line:
                        try:
                            on_line(line)
                        except Exception:
                            pass
                    if stop.is_set():
                        break
            finally:
                try:
                    logf.close()
                except Exception:
                    pass

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        return {"proc": proc, "thread": t, "stop": stop, "cmd": cmd}

    def cancel(self, handle):
        if not handle:
            return
        handle.get("stop") and handle["stop"].set()
        proc = handle.get("proc")
        if proc and proc.poll() is None:
            kill_tree(proc.pid)


class NukeExecutor(BaseExecutor):
    app = "nuke"

    def build_cmd(self, job: dict):
        launcher = _which(self.settings.get("nuke_launcher") or "nuke")
        script = job.get("source_file") or ""
        write = job.get("target") or ""
        fr = job.get("frames") or {}
        start, end, step = fr.get("start", 1), fr.get("end", 1), fr.get("step", 1)
        cores = int((job.get("resources") or {}).get("cpu_cores") or 0)
        cmd = [launcher, "-x"]
        if cores > 0:
            cmd += ["-m", str(cores)]
        if write:
            cmd += ["-X", write]
        if step and int(step) != 1:
            cmd += ["-F", "%d-%dx%d" % (start, end, step)]
        else:
            cmd += ["-F", "%d-%d" % (start, end)]
        cmd.append(script)
        return cmd


class BlenderExecutor(BaseExecutor):
    app = "blender"

    def build_cmd(self, job: dict):
        launcher = _which(self.settings.get("blender_launcher") or "blender")
        blend = job.get("source_file") or ""
        fr = job.get("frames") or {}
        start, end, step = int(fr.get("start", 1)), int(fr.get("end", 1)), int(fr.get("step", 1))
        extra = job.get("extra") or {}
        scene = extra.get("scene") or ""
        view_layer = extra.get("view_layer") or ""
        res_x = extra.get("resolution_x")
        res_y = extra.get("resolution_y")
        res_pct = extra.get("resolution_percentage")
        fps = extra.get("fps")
        device = extra.get("device") or "CPU"   # CPU or GPU
        threads = int((job.get("resources") or {}).get("cpu_cores") or 0)
        # Write a temp override script (for-loops are invalid in --python-expr one-liners)
        lines = ["import bpy", "scene = bpy.context.scene"]
        if scene:
            lines += [
                "sc = bpy.data.scenes.get(%r)" % scene,
                "if sc is not None:",
                "    try:",
                "        bpy.context.window.scene = sc",
                "    except Exception:",
                "        pass",
                "    scene = sc",
            ]
        lines += [
            "scene.frame_start = %d" % start,
            "scene.frame_end = %d" % end,
            "scene.frame_step = %d" % step,
        ]
        if res_x:
            lines.append("scene.render.resolution_x = %d" % int(res_x))
        if res_y:
            lines.append("scene.render.resolution_y = %d" % int(res_y))
        if res_pct:
            lines.append("scene.render.resolution_percentage = %d" % int(res_pct))
        if fps:
            lines.append("scene.render.fps = %d" % int(fps))
        if threads > 0:
            lines += [
                "scene.render.threads_mode = 'FIXED'",
                "scene.render.threads = %d" % threads,
            ]
        if view_layer:
            lines += [
                "for vl in scene.view_layers:",
                "    vl.use = (vl.name == %r)" % view_layer,
            ]
        if str(device).upper() == "GPU":
            lines += [
                "prefs = bpy.context.preferences.addons.get('cycles')",
                "if prefs:",
                "    cprefs = prefs.preferences",
                "    try:",
                "        cprefs.compute_device_type = 'CUDA'",
                "    except Exception:",
                "        try:",
                "            cprefs.compute_device_type = 'HIP'",
                "        except Exception:",
                "            pass",
                "    for d in getattr(cprefs, 'devices', []) or []:",
                "        d.use = getattr(d, 'type', '') != 'CPU'",
                "    scene.cycles.device = 'GPU'",
            ]
        script_path = (job.get("log_path") or "/tmp/paai_rq") + ".blender_override.py"
        os.makedirs(os.path.dirname(script_path) or ".", exist_ok=True)
        with open(script_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        cmd = [launcher, "-b", blend]
        if scene:
            cmd += ["-S", scene]
        cmd += ["--python", script_path, "-a"]
        return cmd


class ComfyUIExecutor(BaseExecutor):
    """Submit to ComfyUI HTTP API; poll /history for completion. No local process tree."""
    app = "comfyui"

    def start(self, job: dict, on_line=None):
        extra = job.get("extra") or {}
        server = (extra.get("server_url") or "").rstrip("/")
        if not server:
            servers = self.settings.get("comfyui_servers") or []
            server = (servers[0]["url"] if servers else "http://127.0.0.1:8188").rstrip("/")
        workflow = extra.get("workflow") or extra.get("prompt")
        if isinstance(workflow, str):
            workflow = json.loads(workflow)
        client_id = "paai_" + job["id"]
        repeats = max(1, int(job.get("repeats") or 1))
        randomize = bool(extra.get("randomize_seed"))
        log_path = job.get("log_path") or os.devnull
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        stop = threading.Event()
        state = {"prompt_ids": [], "done": False, "error": "", "exitcode": None, "paused": False}

        def log(msg):
            with open(log_path, "a") as f:
                f.write(msg + "\n")
            if on_line:
                on_line(msg + "\n")

        def post_prompt(prompt):
            body = json.dumps({"prompt": prompt, "client_id": client_id}).encode("utf-8")
            req = urllib.request.Request(
                server + "/prompt", data=body,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))

        def poll_done(prompt_id):
            url = server + "/history/" + prompt_id
            try:
                with urllib.request.urlopen(url, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                entry = data.get(prompt_id) or {}
                if entry:
                    progress.apply_comfy_history(job, entry)
                    st = (entry.get("status") or {})
                    if st.get("completed") or st.get("status_str") == "success":
                        return True
                    if st.get("status_str") == "error":
                        state["error"] = str(st)
                        return "error"
            except Exception:
                pass
            return False

        def runner():
            try:
                log("===== ComfyUI %s → %s =====" % (job["id"], server))
                for i in range(repeats):
                    if stop.is_set():
                        break
                    prompt = json.loads(json.dumps(workflow))  # deep copy
                    if randomize:
                        _randomize_seeds(prompt)
                    log("repeat %d/%d posting..." % (i + 1, repeats))
                    res = post_prompt(prompt)
                    pid = res.get("prompt_id") or res.get("promptId")
                    state["prompt_ids"].append(pid)
                    log("prompt_id=%s" % pid)
                    # poll
                    while not stop.is_set():
                        if state.get("paused"):
                            time.sleep(0.4)
                            continue
                        r = poll_done(pid)
                        if r is True:
                            pct = round(100.0 * (i + 1) / repeats, 2)
                            job.setdefault("progress", {})["percent"] = pct
                            job["progress"]["message"] = "repeat %d/%d done" % (i + 1, repeats)
                            if on_line:
                                on_line("progress %s%%\n" % pct)
                            break
                        if r == "error":
                            raise RuntimeError(state["error"] or "comfy error")
                        time.sleep(0.8)
                state["done"] = True
                state["exitcode"] = 0 if not stop.is_set() else 1
                log("===== DONE =====")
            except Exception as e:
                state["error"] = str(e)
                state["exitcode"] = 1
                log("ERROR: %s" % e)

        t = threading.Thread(target=runner, daemon=True)
        t.start()

        class FakeProc:
            def poll(self):
                if t.is_alive():
                    return None
                return state.get("exitcode")
            @property
            def pid(self):
                return None
            def wait(self, timeout=None):
                t.join(timeout)

        return {"proc": FakeProc(), "thread": t, "stop": stop, "cmd": ["comfyui", server], "state": state}

    def cancel(self, handle):
        if not handle:
            return
        handle.get("stop") and handle["stop"].set()
        state = handle.get("state") or {}
        state["paused"] = False
        # Ask ComfyUI to interrupt the current prompt
        try:
            extra_server = None
            # server URL was captured in start(); recover from cmd list
            cmd = handle.get("cmd") or []
            server = cmd[1] if len(cmd) > 1 else "http://127.0.0.1:8188"
            body = b"{}"
            req = urllib.request.Request(
                server.rstrip("/") + "/interrupt", data=body,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            urllib.request.urlopen(req, timeout=5).read()
        except Exception as e:
            print("[PAAI RQ] comfy interrupt:", e)



def _randomize_seeds(prompt: dict):
    import random
    for node in (prompt or {}).values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") or {}
        for k in list(inputs.keys()):
            if "seed" in k.lower() and isinstance(inputs[k], int):
                inputs[k] = random.randint(0, 2**31 - 1)


def get_executor(app: str, settings: dict) -> BaseExecutor:
    return {
        "nuke": NukeExecutor,
        "blender": BlenderExecutor,
        "comfyui": ComfyUIExecutor,
    }.get(app, BaseExecutor)(settings)


def test_launcher(path: str, kind: str):
    """Return {ok, path, version, error}."""
    resolved = _which(path or ("nuke" if kind == "nuke" else "blender" if kind == "blender" else path))
    if not resolved:
        return {"ok": False, "path": path, "error": "not found"}
    if not os.path.isfile(resolved) and kind != "comfyui":
        # still try running - might be on PATH name only
        pass
    try:
        if kind == "comfyui":
            url = (path or "").rstrip("/") + "/system_stats"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "path": path, "version": data, "error": ""}
        flag = "-v" if kind == "nuke" else "--version"
        r = subprocess.run([resolved, flag], capture_output=True, text=True, timeout=20)
        out = (r.stdout or r.stderr or "").strip().splitlines()
        ver = out[0] if out else ("exit %s" % r.returncode)
        return {"ok": r.returncode == 0 or bool(out), "path": resolved, "version": ver, "error": ""}
    except Exception as e:
        return {"ok": False, "path": resolved, "version": "", "error": str(e)}
