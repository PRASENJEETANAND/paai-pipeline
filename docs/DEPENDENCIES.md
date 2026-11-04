# Dependencies

## ComfyUI custom node

Required / recommended (see `comfyui/comfyui_paai_pipeline/requirements.txt`):

| Package | Why |
|---------|-----|
| `OpenEXR>=3.2` | Multi-layer EXR |
| `Imath` | OpenEXR companion |
| `opencv-python-headless` | 16-bit/float PNG & TIFF, movies |
| `numpy` | Image buffers (usually already present) |
| `Pillow` | Fallback image I/O |

### Portable ComfyUI (Windows embedded Python)

```bat
.\python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\comfyui_paai_pipeline\requirements.txt
```

### venv / manual

```bash
pip install -r ComfyUI/custom_nodes/comfyui_paai_pipeline/requirements.txt
# or:
pip install "OpenEXR>=3.2" Imath opencv-python-headless numpy Pillow
```

### Verify

```bash
python -c "import OpenEXR, Imath, cv2; print('OK', OpenEXR.__version__ if hasattr(OpenEXR,'__version__') else 'OpenEXR', cv2.__version__)"
```

### Common errors

- **`ModuleNotFoundError: OpenEXR`** — pip into the *same* interpreter ComfyUI uses (embedded vs system).
- **`DLL load failed` on Windows** — install [Microsoft VC++ redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist); retry `pip install --force-reinstall OpenEXR`.
- **Wrong pip** — `where python` / `where pip` must match the ComfyUI runtime.

### Fixed listen address / port tip

In your ComfyUI `.bat` / launch command:

```bat
.\python_embeded\python.exe -s ComfyUI\main.py --listen 127.0.0.1 --port 8188
```

Second GPU instance:

```bat
.\python_embeded\python.exe -s ComfyUI\main.py --listen 127.0.0.1 --port 8189 --cuda-device 1
```

Point the Render Queue Comfy job **server URL** at that host/port.

## Nuke 13–17

No extra packages. Uses built-in Python (3.7–3.11 depending on version) and PySide2/PySide6 shipped with Nuke.

## Blender 4.2–5.1

No extra packages. Bundled Python is enough. Optional PySide6 for the Qt Render Browser (falls back to web UI).

## Render Queue

- **Required:** Python 3.8+ standard library only.
- **Optional:** `psutil` — richer Windows process-tree pause/resume; without it a `CreateToolhelp32Snapshot` fallback is used.

```bash
pip install psutil   # optional
python -m paai_render_queue
```
