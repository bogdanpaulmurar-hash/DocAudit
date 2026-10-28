"""Pornirea obișnuită: `pythonw -m docaudit` (fără consolă) → iconiță în tray + interfața în browser.

- Dacă DocAudit rulează deja, doar deschide browserul la el (o singură instanță).
- Fără pystray (opțional, `pip install -e .[tray]`), interfața pornește oricum, fără iconiță în tray.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
import webbrowser

from . import __version__
from .i18n import t
from .paths import data_dir
from .settings import load_settings


INSTANCE_FILE = "instance.json"  # portul, jetonul și versiunea instanței care rulează (doar local)


def _running_version(port: int) -> str | None:
    """„DocAudit/0.1.4” dacă pe port rulează DocAudit (versiunile vechi spun doar „DocAudit”), altfel None."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/icon.svg", timeout=1) as r:  # doar local
            server = r.headers.get("Server", "").split(" ")[0]
            return server if server.startswith("DocAudit") else None
    except Exception:
        return None


def _already_running(port: int) -> bool:
    return _running_version(port) is not None


def _ask_old_to_quit(port: int) -> bool:
    """Îi cere instanței vechi să se închidă, cu jetonul ei din instance.json. True dacă portul s-a eliberat."""
    try:
        info = json.loads((data_dir() / INSTANCE_FILE).read_text("utf-8"))
        if int(info.get("port", 0)) != port:
            return False
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/quit", data=b"{}", method="POST",
                                     headers={"X-DocAudit-Token": info["token"], "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2).close()
    except Exception:
        return False
    for _ in range(30):
        if _running_version(port) is None:
            return True
        time.sleep(0.2)
    return False


def _write_instance(server) -> None:
    try:
        path = data_dir() / INSTANCE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"port": server.server_address[1], "token": server.token,
                                    "version": __version__, "pid": os.getpid()}), encoding="utf-8")
    except OSError:
        pass


def start_server(port: int):
    """Serverul pe portul din setări. Aceeași versiune rulează deja → None (se deschide doar browserul).
    Altă versiune rulează → îi cerem să se închidă; dacă nu vrea (versiune veche), pornim pe alt port."""
    from .ui.server import DocAuditServer

    try:
        return DocAuditServer("127.0.0.1", port)
    except OSError:
        pass
    running = _running_version(port)
    if running == f"DocAudit/{__version__}":
        return None
    if running and _ask_old_to_quit(port):
        for _ in range(15):
            try:
                return DocAuditServer("127.0.0.1", port)
            except OSError:
                time.sleep(0.2)
    return DocAuditServer("127.0.0.1", 0)


def run_app(open_browser: bool = True) -> int:  # pragma: no cover - pornire interactivă
    settings = load_settings()
    server = start_server(settings.port)
    if server is None:
        webbrowser.open(f"http://127.0.0.1:{settings.port}/")
        return 0
    _write_instance(server)
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

    server.on_quit = lambda: tray_icon.stop()
    menu = pystray.Menu(
        pystray.MenuItem(t("tray.open", settings.lang), lambda *_: webbrowser.open(server.url), default=True),
        pystray.MenuItem(t("tray.quit", settings.lang), quit_app),
    )
    tray_icon = pystray.Icon("DocAudit", image, t("tray.title", settings.lang), menu)
    tray_icon.run()
    return 0
