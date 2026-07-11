import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
import webview

from ..config.env import load_env

ASSETS = Path(__file__).parent / "assets"
APP_URL = "http://127.0.0.1:8000?desktop=1"


class _Api:
    def close(self) -> None:
        webview.windows[0].destroy()


def _splash_html() -> str:
    idle_uri = (ASSETS / "idle.gif").resolve().as_uri()
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Pipsqueak</title></head>
<body style="margin:0;background:transparent;display:flex;align-items:flex-end;
justify-content:flex-end;height:100vh;padding:24px;box-sizing:border-box;">
  <img src="{idle_uri}" style="width:280px;height:280px;object-fit:contain;" alt="Pipsqueak">
</body>
</html>"""


def _switch_when_ready(window: webview.Window, url: str, timeout: float = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/", timeout=1)
            window.load_url(url)
            return
        except Exception:
            time.sleep(0.5)


def main() -> None:
    load_env()

    threading.Thread(
        target=lambda: uvicorn.run(
            "src.frontend.server:app",
            host="127.0.0.1",
            port=8000,
            reload=False,
        ),
        daemon=True,
    ).start()

    window = webview.create_window(
        "Pipsqueak",
        html=_splash_html(),
        width=760,
        height=520,
        frameless=True,
        on_top=True,
        transparent=True,
        js_api=_Api(),
    )
    threading.Thread(
        target=_switch_when_ready,
        args=(window, APP_URL),
        daemon=True,
    ).start()
    webview.start()
