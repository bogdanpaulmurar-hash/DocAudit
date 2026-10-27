"""Rularea comparării pe un folder grupat și salvarea rezultatului în findings.json.

Citește pages.jsonl și groups.json; nu modifică nimic din ele.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..group.run import GROUPS_FILE, load_groups
from ..model import read_pages
from .analyze import CompareSettings, GroupReport, compare_group, shared_images

FINDINGS_FILE = "findings.json"
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class CompareResult:
    groups: list[GroupReport]
    shared_images: list

    def findings(self):
        return [f for g in self.groups for f in g.findings]


def run_compare(folder: Path, settings: CompareSettings | None = None, save: bool = True) -> CompareResult:
    settings = settings or CompareSettings()
    if not (folder / GROUPS_FILE).is_file():
        raise FileNotFoundError(folder / GROUPS_FILE)
    pages = {p.id: p for p in read_pages(folder)}
    reports = []
    for g in load_groups(folder)["groups"]:
        members = [pages[pid] for pid in g["pages"] if pid in pages]
        if len(members) >= 2:
            reports.append(compare_group(g["id"], members, settings))

    def rank(r: GroupReport) -> tuple:
        sev = min((_SEVERITY_ORDER[f.severity] for f in r.findings), default=3)
        return (sev, -len(r.findings), r.group)

    reports.sort(key=rank)
    result = CompareResult(reports, shared_images(list(pages.values())))
    if save:
        data = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "settings": asdict(settings),
            "groups": [r.to_dict() for r in reports],
            "shared_images": [f.to_dict() for f in result.shared_images],
        }
        (folder / FINDINGS_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8", newline="\n")
    return result


def load_findings(folder: Path) -> dict:
    return json.loads((folder / FINDINGS_FILE).read_text("utf-8"))
