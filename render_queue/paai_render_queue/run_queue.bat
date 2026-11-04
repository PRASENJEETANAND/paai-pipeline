@echo off
cd /d "%~dp0\.."
python -m paai_render_queue %*
