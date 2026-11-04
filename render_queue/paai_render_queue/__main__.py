"""python -m paai_render_queue [--port 8790] [--data ~/Documents/PAAI Render Queue]"""
from __future__ import annotations
import argparse
from . import config
from . import server


def main(argv=None):
    ap = argparse.ArgumentParser(description="PAAI Render Queue")
    ap.add_argument("--host", default=config.DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--data", "--root", dest="data", default="",
                    help="Data folder (default: <Documents>/PAAI Render Queue). "
                         "Also written to ~/.paai/render_queue_location.json")
    args = ap.parse_args(argv)
    server.serve(host=args.host, port=args.port, data_folder=args.data or None)


if __name__ == "__main__":
    main()
