"""Corecturile utilizatorului la grupare, păstrate între rulări.

- „Unește”: două pagini ajung mereu în același grup (must_link).
- „Nu face parte din grup”: pagina nu mai stă cu niciuna din paginile grupului (cannot_link).
Fișierul stă lângă datele extrase: <folder>/group_overrides.json.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

FILE = "group_overrides.json"


@dataclass
class GroupOverrides:
    must_link: list[list[str]] = field(default_factory=list)
    cannot_link: list[list[str]] = field(default_factory=list)

    @classmethod
    def load(cls, folder: Path) -> "GroupOverrides":
        path = folder / FILE
        if not path.is_file():
            return cls()
        d = json.loads(path.read_text("utf-8"))
        return cls(must_link=d.get("must_link", []), cannot_link=d.get("cannot_link", []))

    def save(self, folder: Path) -> None:
        (folder / FILE).write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8", newline="\n")

    @staticmethod
    def _pair(a: str, b: str) -> list[str]:
        return sorted([a, b])

    def merge(self, a: str, b: str) -> None:
        pair = self._pair(a, b)
        self.cannot_link = [p for p in self.cannot_link if p != pair]
        if pair not in self.must_link:
            self.must_link.append(pair)

    def detach(self, page: str, group_pages: list[str]) -> None:
        for other in group_pages:
            if other == page:
                continue
            pair = self._pair(page, other)
            self.must_link = [p for p in self.must_link if p != pair]
            if pair not in self.cannot_link:
                self.cannot_link.append(pair)
