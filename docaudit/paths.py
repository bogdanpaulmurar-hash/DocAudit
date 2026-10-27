"""Unde stau datele DocAudit pe calculator (niciodată în clona repo-ului din Google Drive)."""

from __future__ import annotations

import os
from pathlib import Path

from .model import PAGES_FILE


def data_dir() -> Path:
    """Unde stau datele extrase. Implicit pe disc local, NU în folderul sincronizat al repo-ului.

    Documentația companiei nu are voie să ajungă în Google Drive prin clona din G:\\My Drive.
    """
    if os.environ.get("DOCAUDIT_DATA"):
        return Path(os.environ["DOCAUDIT_DATA"])
    if os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "DocAudit" / "data"
    return Path.home() / ".local" / "share" / "docaudit"


def backups_dir() -> Path:
    """Copiile de siguranță ale paginilor, făcute înainte de orice scriere în OneNote."""
    return data_dir() / "_backups"


def resolve_folder(arg: Path) -> Path:
    """Acceptă o cale sau doar numele unei extrageri din folderul de date (ex. „demo”)."""
    if arg.exists() or arg.is_absolute() or len(arg.parts) > 1:
        return arg
    return data_dir() / arg


def datasets() -> list[Path]:
    """Extragerile din folderul de date (foldere cu pages.jsonl), cele mai noi întâi."""
    root = data_dir()
    if not root.is_dir():
        return []
    found = [p for p in root.iterdir() if (p / PAGES_FILE).is_file()]
    return sorted(found, key=lambda p: (p / PAGES_FILE).stat().st_mtime, reverse=True)
