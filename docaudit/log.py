"""Logul tehnic DocAudit: ce s-a rulat, cât a durat, ce a mers și ce nu.

Trei locuri:
1. local, `data_dir()/logs/docaudit.log` (mereu);
2. copie în folderul `logs/` al clonei DocAudit din Google Drive (implicit pornit, se
   oprește din Setări), ca logul de pe alte laptopuri să poată fi citit de acolo;
3. în memorie (ultimele rânduri), pentru ecranul „Setări” → „Log tehnic” și progresul extragerii.

Logul NU conține documentația: fără titluri, nume de notebook-uri / secțiuni, text sau
id-uri de pagini. Doar numere, durate, tipuri de eroare și locul din cod. Căile din
folderul utilizatorului se scurtează la `~`, numele de utilizator se ascunde.
"""

from __future__ import annotations

import collections
import getpass
import hashlib
import logging
import logging.handlers
import os
import platform
import socket
import sys
import threading
from pathlib import Path

from . import __version__
from .paths import data_dir

LOGGER = "docaudit"
LOG_FILE = "docaudit.log"
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_MAX_BYTES = 1_000_000
_lock = threading.Lock()
_memory: collections.deque[str] = collections.deque(maxlen=400)
_state: dict[str, object] = {"configured": False, "shared": None}


def get(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{LOGGER}.{name}" if name else LOGGER)


def machine_label() -> str:
    """Un nume scurt pentru laptop, fără numele real al calculatorului (de ex. „pc-3fa9c1”)."""
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    raw = f"{socket.gethostname()}|{user}"
    return "pc-" + hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:6]


def repo_root() -> Path | None:
    """Clona DocAudit din care rulează aplicația (instalare editabilă), dacă e una."""
    root = Path(__file__).resolve().parents[1]
    if (root / "pyproject.toml").is_file() and (root / "docaudit").is_dir():
        return root
    return None


def shared_dir(custom: str = "") -> Path | None:
    """Folderul din Drive unde ajunge copia logului: cel ales în setări sau `<clona>/logs`."""
    if custom.strip():
        return Path(os.path.expandvars(os.path.expanduser(custom.strip())))
    root = repo_root()
    if root is None:
        return None
    try:  # niciodată în folderul de date (acolo e deja logul local)
        root.relative_to(data_dir())
        return None
    except ValueError:
        return root / "logs"


class _Redact(logging.Filter):
    """Scurtează căile din folderul utilizatorului și ascunde numele de utilizator."""

    def __init__(self) -> None:
        super().__init__()
        home = str(Path.home())
        self._pairs = [(home, "~"), (home.replace("\\", "/"), "~")]
        try:
            user = getpass.getuser()
        except Exception:
            user = ""
        if len(user) >= 3:
            self._pairs += [(user, "<user>"), (user.upper(), "<user>"), (user.lower(), "<user>")]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        for old, new in self._pairs:
            if old:
                msg = msg.replace(old, new)
                if record.exc_text:
                    record.exc_text = record.exc_text.replace(old, new)
        record.msg, record.args = msg, None
        return True


class _MemoryHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
        except Exception:
            return
        with _lock:
            _memory.extend(line.splitlines() or [""])


def _file_handler(path: Path) -> logging.Handler | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        h = logging.handlers.RotatingFileHandler(path, maxBytes=_MAX_BYTES, backupCount=3, encoding="utf-8",
                                                 delay=True)
    except OSError:
        return None
    h.setFormatter(logging.Formatter(FORMAT))
    return h


def setup(share: bool | None = None, custom_dir: str | None = None, force: bool = False) -> dict:
    """Pornește logul (o dată pe proces; `force` îl refă după o schimbare în setări)."""
    if share is None or custom_dir is None:
        from .settings import load_settings

        s = load_settings()
        share = s.share_log if share is None else share
        custom_dir = s.log_dir if custom_dir is None else custom_dir
    logger = logging.getLogger(LOGGER)
    with _lock:
        if _state["configured"] and not force:
            return info()
        for h in list(logger.handlers):
            logger.removeHandler(h)
            h.close()
        logger.setLevel(logging.INFO)
        logger.propagate = False
        redact = _Redact()
        mem = _MemoryHandler()
        mem.setFormatter(logging.Formatter(FORMAT, "%H:%M:%S"))
        handlers: list[logging.Handler] = [mem]
        local = _file_handler(data_dir() / "logs" / LOG_FILE)
        if local:
            handlers.append(local)
        shared_path = None
        if os.environ.get("DOCAUDIT_LOG_SHARE") == "0":  # testele și cine nu vrea copia în Drive
            share = False
        if share:
            folder = shared_dir(custom_dir or "")
            if folder is not None:
                shared_path = folder / f"{machine_label()}.log"
                h = _file_handler(shared_path)
                if h:
                    handlers.append(h)
                else:
                    shared_path = None
        for h in handlers:
            h.addFilter(redact)
            logger.addHandler(h)
        _state.update(configured=True, shared=shared_path)
    get().info("DocAudit %s pornit · %s · Python %s · %s · %s", __version__, platform.platform(),
               platform.python_version(), machine_label(), "pythonw" if sys.stdout is None else "consolă")
    return info()


def info() -> dict:
    shared = _state.get("shared")
    return {"local": str(data_dir() / "logs" / LOG_FILE), "shared": str(shared) if shared else None,
            "machine": machine_label()}


def tail(n: int = 200) -> list[str]:
    with _lock:
        return list(_memory)[-n:]


def describe_error(e: BaseException) -> str:
    """Tipul și mesajul erorii, fără conținut de pagină (mesajele COM nu conțin text din pagini)."""
    text = str(e).strip().replace("\n", " ")
    return f"{type(e).__name__}: {text[:500]}" if text else type(e).__name__
