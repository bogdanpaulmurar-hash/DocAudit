"""Pornirea obișnuită: `pythonw -m docaudit` (fără consolă) → iconiță în tray + interfața în browser.

- Dacă DocAudit rulează deja, doar deschide browserul la el (o singură instanță).
- Fără pystray (opțional, `pip install -e .[tray]`), interfața pornește oricum, fără iconiță în tray.
"""

from __future__ import annotations

import threading
import urllib.request
import webbrowser

from .i18n import t
from .settings import load_settings


def _already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/icon.svg", timeout=1) as r:  # doar local
            return r.headers.get("Server", "").startswith("DocAudit")
    except Exception:
        return False


def run_app(open_browser: bool = True) -> int:  # pragma: no cover - pornire interactivă
    from .ui.server import DocAuditServer

    settings = load_settings()
    try:
        server = DocAuditServer("127.0.0.1", settings.port)
    except OSError:
        if _already_running(settings.port):
            webbrowser.open(f"http://127.0.0.1:{settings.port}/")
            return 0
        server = DocAuditServer("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if open_browser:
        webbrowser.open(server.url)
    try:
        import pystray  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        try:
            thread.join()
        except KeyboardInterrupt:
            pass
        server.shutdown()
        return 0

    from .icon import render

    image = Image.frombytes("RGBA", (64, 64), render(64))

    def quit_app(icon, _item) -> None:
        icon.stop()
        server.shutdown()

    menu = pystray.Menu(
        pystray.MenuItem(t("tray.open", settings.lang), lambda *_: webbrowser.open(server.url), default=True),
        pystray.MenuItem(t("tray.quit", settings.lang), quit_app),
    )
    pystray.Icon("DocAudit", image, t("tray.title", settings.lang), menu).run()
    return 0
