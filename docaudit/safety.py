"""Garanțiile „doar local” și „fără scriere în sursă”, verificabile în teste.

- no_network(): blochează orice conexiune de rețea cât timp e activ.
- tree_digest(): amprenta unui folder, ca să dovedim că analiza nu l-a modificat.
- is_loopback(): serverul UI acceptă doar adrese locale.
"""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class NetworkBlockedError(RuntimeError):
    """O componentă a încercat să iasă în rețea în timp ce rețeaua era blocată."""


@contextmanager
def no_network() -> Iterator[None]:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise NetworkBlockedError("Acces la rețea blocat de DocAudit")

    saved = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo)
    socket.socket.connect = blocked  # type: ignore[method-assign]
    socket.socket.connect_ex = blocked  # type: ignore[method-assign]
    socket.create_connection = blocked  # type: ignore[assignment]
    socket.getaddrinfo = blocked  # type: ignore[assignment]
    try:
        yield
    finally:
        (socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo) = saved  # type: ignore[method-assign]


def tree_digest(root: Path) -> str:
    """SHA-256 peste căile relative și conținutul tuturor fișierelor din root."""
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(path.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
