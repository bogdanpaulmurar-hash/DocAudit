"""Rularea grupării pe un folder extras și salvarea rezultatului în groups.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..model import read_pages
from .cluster import Group, cluster
from .overrides import GroupOverrides
from .semantic import semantic_scores
from .similarity import PairScore, SimilaritySettings, score_pairs

GROUPS_FILE = "groups.json"
DEFAULT_THRESHOLD = 0.6


@dataclass
class GroupingResult:
    threshold: float
    groups: list[Group]
    ungrouped: list[str]
    semantic: bool

    def to_dict(self, settings: SimilaritySettings) -> dict:
        return {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "threshold": self.threshold,
            "semantic": self.semantic,
            "settings": {k: v for k, v in asdict(settings).items() if k != "title_noise"},
            "groups": [g.to_dict() for g in self.groups],
            "ungrouped": self.ungrouped,
        }


def compute_pairs(folder: Path, settings: SimilaritySettings, use_semantic: bool = False) -> tuple[list, list[PairScore]]:
    pages = read_pages(folder)
    sem = semantic_scores(pages) if use_semantic else None
    return pages, score_pairs(pages, settings, sem)


def run_grouping(folder: Path, threshold: float = DEFAULT_THRESHOLD,
                 settings: SimilaritySettings | None = None, use_semantic: bool = False,
                 save: bool = True) -> GroupingResult:
    settings = settings or SimilaritySettings()
    pages, pairs = compute_pairs(folder, settings, use_semantic)
    ov = GroupOverrides.load(folder)
    groups, alone = cluster([p.id for p in pages], pairs, threshold, ov.must_link, ov.cannot_link,
                            titles={p.id: p.title for p in pages})
    result = GroupingResult(threshold, groups, alone, use_semantic)
    if save:
        (folder / GROUPS_FILE).write_text(
            json.dumps(result.to_dict(settings), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
    return result


def scan_thresholds(folder: Path, thresholds: list[float], settings: SimilaritySettings | None = None,
                    use_semantic: bool = False) -> list[tuple[float, int, int]]:
    """Pentru fiecare prag: (prag, nr. grupuri, pagini grupate). Scorurile se calculează o dată."""
    settings = settings or SimilaritySettings()
    pages, pairs = compute_pairs(folder, settings, use_semantic)
    ov = GroupOverrides.load(folder)
    ids = [p.id for p in pages]
    out = []
    for t in thresholds:
        groups, _ = cluster(ids, pairs, t, ov.must_link, ov.cannot_link)
        out.append((t, len(groups), sum(len(g.pages) for g in groups)))
    return out


def load_groups(folder: Path) -> dict:
    return json.loads((folder / GROUPS_FILE).read_text("utf-8"))
