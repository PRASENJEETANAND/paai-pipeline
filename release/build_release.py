#!/usr/bin/env python3
"""Build the four PAAI install zips into dist/.

Layouts match the shipping packs:
  - nuke_paai_pipeline.zip          → flat (files at archive root for ~/.nuke)
  - blender_paai_pipeline.zip       → top folder blender_paai_pipeline/
  - comfyui_paai_pipeline.zip       → top folder comfyui_paai_pipeline/
  - paai_render_queue.zip           → top folder paai_render_queue/
"""
from __future__ import print_function

import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SKIP = {"__pycache__", ".git", ".DS_Store"}


def should_skip(path: Path) -> bool:
    return any(part in SKIP or part.endswith(".pyc") for part in path.parts)


def zip_tree(src: Path, dest: Path, *, flat: bool, top_name: str = None):
    if dest.exists():
        dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.rglob("*")):
            if should_skip(p) or not p.is_file():
                continue
            rel = p.relative_to(src)
            if flat:
                arc = str(rel)
            else:
                arc = str(Path(top_name or src.name) / rel)
            z.write(p, arc)
    print("wrote", dest, dest.stat().st_size, "bytes")


def main():
    DIST.mkdir(parents=True, exist_ok=True)
    zip_tree(ROOT / "nuke", DIST / "nuke_paai_pipeline.zip", flat=True)
    zip_tree(
        ROOT / "blender" / "blender_paai_pipeline",
        DIST / "blender_paai_pipeline.zip",
        flat=False,
        top_name="blender_paai_pipeline",
    )
    zip_tree(
        ROOT / "comfyui" / "comfyui_paai_pipeline",
        DIST / "comfyui_paai_pipeline.zip",
        flat=False,
        top_name="comfyui_paai_pipeline",
    )
    zip_tree(
        ROOT / "render_queue" / "paai_render_queue",
        DIST / "paai_render_queue.zip",
        flat=False,
        top_name="paai_render_queue",
    )
    print("OK — zips in", DIST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
