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
        return errors

    def to_dict(self) -> dict:
        return asdict(self)


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
