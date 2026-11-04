#!/usr/bin/env python3
"""Fake Nuke that prints Frame lines like the real renderer."""
import sys, time, argparse
# parse -F start-endxstep and ignore the rest
frames = "1-10"
args = sys.argv[1:]
for i, a in enumerate(args):
    if a == "-F" and i + 1 < len(args):
        frames = args[i + 1]
        break
step = 1
if "x" in frames:
    rng, step_s = frames.split("x", 1)
    step = int(step_s)
else:
    rng = frames
start, end = [int(x) for x in rng.split("-", 1)]
total = (end - start) // step + 1
print("Fake Nuke starting", start, end, step, flush=True)
for i, f in enumerate(range(start, end + 1, step), 1):
    print("Frame %d (%d of %d)" % (f, i, total), flush=True)
    time.sleep(0.15)
print("Write complete", flush=True)
sys.exit(0)
