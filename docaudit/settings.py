"""Setările utilizatorului, în data_dir()/settings.json (local, lângă date).

Scrierea în OneNote e oprită implicit („mod doar citire”) și se pornește doar din setări.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .i18n import LANGUAGES
from .paths import data_dir

SETTINGS_FILE = "settings.json"


@dataclass
class Settings:
    lang: str = "ro"
    threshold: float = 0.6
    semantic: bool = False
    archive_section: str = "Arhivă"
    stale_prefix: str = "[ÎNVECHIT] "
    exclude_sections: list[str] = field(default_factory=lambda: ["Arhivă"])
    write_enabled: bool = False  # mod doar citire până îl oprești tu
    port: int = 8765
    share_log: bool = True  # copia logului tehnic (fără conținut) în folderul DocAudit din Google Drive
    log_dir: str = ""  # gol = folderul `logs` din clona DocAudit
    # „Export pentru bot”
    bot_level: str = "top"  # un document pe: notebook | top (folderul de sus) | section
    bot_max_mb: float = 95.0  # limita botului e 100 MB pe fișier; 5 MB rezervă
    bot_out_dir: str = ""  # gol = <extragere>/bot/out
    bot_skip_stale: bool = True
    bot_skip_duplicates: bool = True

    def validate(self) -> list[str]:
        errors = []
        if self.lang not in LANGUAGES:
            errors.append("lang")
        if not 0 < self.threshold < 1:
            errors.append("threshold")
        if not self.archive_section.strip() or any(c in self.archive_section for c in '\\/:*?"<>|'):
            errors.append("archive_section")
        if not 1024 <= self.port <= 65535:
            errors.append("port")
        if self.bot_level not in ("notebook", "top", "section"):
            errors.append("bot_level")
        if not isinstance(self.bot_max_mb, (int, float)) or not 1 <= self.bot_max_mb <= 2000:
            errors.append("bot_max_mb")
        if self.bot_out_dir and not _local_out_dir_ok(self.bot_out_dir):
            errors.append("bot_out_dir")
        return errors

    def to_dict(self) -> dict:
        return asdict(self)


def _local_out_dir_ok(path: str) -> bool:
    """Folderul documentelor pentru bot: cale completă, nu în clona DocAudit (care e în Google Drive)."""
    p = Path(path)
    if not p.is_absolute():
        return False
    clone = Path(__file__).resolve().parents[1]
    try:
        p.resolve().relative_to(clone)
        return False
    except ValueError:
        return True


def settings_path() -> Path:
    return data_dir() / SETTINGS_FILE


def load_settings() -> Settings:
    path = settings_path()
    if not path.is_file():
        return Settings()
    try:
        raw = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return Settings()
    known = {f.name for f in fields(Settings)}
    s = Settings(**{k: v for k, v in raw.items() if k in known})
    return s if not s.validate() else Settings()


def save_settings(s: Settings) -> Path:
    errors = s.validate()
    if errors:
        raise ValueError(", ".join(errors))
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(s.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def update_settings(changes: dict) -> Settings:
    known = {f.name: f for f in fields(Settings)}
    current = load_settings().to_dict()
    for k, v in changes.items():
        if k in known:
            current[k] = v
    s = Settings(**current)
    save_settings(s)
    return s
