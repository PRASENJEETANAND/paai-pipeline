#!/usr/bin/env python3
"""Fake Blender that prints Fra:N lines."""
import sys, time, re
args = sys.argv[1:]
expr = ""
script = ""
for i, a in enumerate(args):
    if a == "--python-expr" and i + 1 < len(args):
        expr = args[i + 1]
    if a == "--python" and i + 1 < len(args):
        script = args[i + 1]
src = expr
if script:
    try:
        with open(script) as f:
            src = f.read()
    except Exception:
        pass
start = end = step = 1
m = re.search(r"frame_start\s*=\s*(\d+)", src)
if m: start = int(m.group(1))
m = re.search(r"frame_end\s*=\s*(\d+)", src)
if m: end = int(m.group(1))
m = re.search(r"frame_step\s*=\s*(\d+)", src)
if m: step = int(m.group(1))
# allow env override for slow tests
import os
delay = float(os.environ.get("PAAI_FAKE_DELAY", "0.12"))
print("Blender fake render", start, end, step, flush=True)
for f in range(start, end + 1, step):
    print("Fra:%d Mem:40.00M | Time:00:00.10 | Rendering 64 / 64 samples" % f, flush=True)
    time.sleep(delay)
print("Saved: '/tmp/fake.####.png'", flush=True)
sys.exit(0)
