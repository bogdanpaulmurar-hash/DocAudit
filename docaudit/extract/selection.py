"""Ce pagini se verifică: bifele din arbore, salvate ca profil.

O pagină intră în analiză dacă e bifată direct, dacă secțiunea ei e bifată sau
dacă notebook-ul ei e bifat. Fără nicio bifă = tot. Secțiunile excluse (implicit
„Arhivă”) și Coșul OneNote nu intră niciodată.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_ARCHIVE = "Arhivă"
PATH_SEP = "/"


@dataclass
class Selection:
    notebooks: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)  # „Notebook/Grup/Secțiune”
    pages: list[str] = field(default_factory=list)  # id-uri de pagină
    exclude_sections: list[str] = field(default_factory=lambda: [DEFAULT_ARCHIVE])

    @property
    def is_everything(self) -> bool:
        return not (self.notebooks or self.sections or self.pages)

    def includes(self, page_id: str, notebook: str, section_path: list[str]) -> bool:
        full = PATH_SEP.join([notebook, *section_path])
        excluded = {e.casefold() for e in self.exclude_sections}
        if any(s.casefold() in excluded for s in section_path) or full.casefold() in excluded:
            return False
        if self.is_everything:
            return True
        if page_id in self.pages or notebook in self.notebooks:
            return True
        return any(full == s or full.startswith(s + PATH_SEP) for s in self.sections)

    def to_dict(self) -> dict[str, list[str]]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Selection":
        return cls(**{k: list(v) for k, v in d.items() if k in cls.__dataclass_fields__})


_SAFE = re.compile(r"[^\w\- ]+", re.UNICODE)


def profile_path(profiles_dir: Path, name: str) -> Path:
    safe = _SAFE.sub("_", name).strip() or "profil"
    return profiles_dir / f"{safe}.json"


def save_profile(profiles_dir: Path, name: str, selection: Selection) -> Path:
    profiles_dir.mkdir(parents=True, exist_ok=True)
    path = profile_path(profiles_dir, name)
    data = {"name": name, "selection": selection.to_dict()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def load_profile(profiles_dir: Path, name: str) -> Selection:
    data = json.loads(profile_path(profiles_dir, name).read_text("utf-8"))
    return Selection.from_dict(data["selection"])


def list_profiles(profiles_dir: Path) -> list[str]:
    if not profiles_dir.is_dir():
        return []
    return sorted(json.loads(p.read_text("utf-8")).get("name", p.stem) for p in profiles_dir.glob("*.json"))
