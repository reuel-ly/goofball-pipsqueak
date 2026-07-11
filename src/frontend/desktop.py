import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
import webview

from ..config.env import load_env

ASSETS = Path(__file__).parent / "assets"
APP_URL = "http://127.0.0.1:8000?desktop=1"
CHARACTER_SIZE = 280
# Room for level meter + mic/textbox row under the GIF.
INPUT_STACK_HEIGHT = 54
WINDOW_HEIGHT = CHARACTER_SIZE + INPUT_STACK_HEIGHT


class _Api:
    def close(self) -> None:
        webview.windows[0].destroy()


def _splash_html() -> str:
    idle_uri = (ASSETS / "idle.gif").resolve().as_uri()
    size = CHARACTER_SIZE
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Pipsqueak</title>
<style>html,body{{margin:0;width:100%;height:100%;background:transparent!important;overflow:hidden;}}</style>
</head>
<body style="margin:0;background:transparent;width:100%;height:100%;
display:flex;flex-direction:column;">
  <img src="{idle_uri}" style="width:{size}px;height:{size}px;object-fit:contain;display:block;flex:0 0 auto;" alt="Pipsqueak">
  <div style="flex:1;margin:4px 0 0;border-radius:12px;background:rgba(15,17,23,0.55);
    border:1px solid rgba(255,255,255,0.08);"></div>
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


def _clear_form_background(window: webview.Window) -> None:
    """WebView2 can be transparent while the WinForms host still paints white."""
    form = window.native
    if form is None:
        return
    try:
        from System.Drawing import Color

        form.BackColor = Color.Transparent
        webview_ctrl = getattr(form, "browser", None) or getattr(form, "webview", None)
        if webview_ctrl is not None:
            webview_ctrl.DefaultBackgroundColor = Color.Transparent
    except Exception:
        pass


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
        width=CHARACTER_SIZE,
        height=WINDOW_HEIGHT,
        frameless=True,
        on_top=True,
        transparent=True,
        # Must be a 6-digit hex triplet (8-digit alpha is rejected).
        # With transparent=True WebView2 overrides this to Color.Transparent;
        # dark matches the app if anything flashes first.
        shadow=False,
        js_api=_Api(),
    )
    window.events.shown += lambda: _clear_form_background(window)
    window.events.loaded += lambda: _clear_form_background(window)
    threading.Thread(
        target=_switch_when_ready,
        args=(window, APP_URL),
        daemon=True,
    ).start()
    webview.start()
