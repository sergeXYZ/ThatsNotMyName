#!/usr/bin/env python3
"""That's Not My Name — macOS window around the local web UI."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(getattr(sys, "_MEIPASS"))
else:
    ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["TNMN_APP"] = "1"

import webview

from web_ui import HOST, app, ensure_assets


def free_port(start: int = 8765) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((HOST, port))
            except OSError:
                continue
            return port
    raise SystemExit("No free local port for That's Not My Name.")


def wait_until_up(url: str) -> None:
    for _ in range(50):
        try:
            with urllib.request.urlopen(url, timeout=0.3) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    raise SystemExit(f"The window server did not start: {url}")


def main() -> None:
    ensure_assets()
    port = free_port()
    url = f"http://{HOST}:{port}/"

    def serve() -> None:
        app.run(host=HOST, port=port, debug=False, threaded=True, use_reloader=False)

    threading.Thread(target=serve, daemon=True).start()
    wait_until_up(url)
    webview.create_window(
        "That's Not My Name",
        url,
        width=560,
        height=920,
        min_size=(480, 640),
        background_color="#1f8fe0",
    )
    webview.start()


if __name__ == "__main__":
    main()
