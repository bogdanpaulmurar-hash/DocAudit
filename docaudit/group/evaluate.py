"""Cât de bine grupează DocAudit eșantionul: precizie, acoperire și F1 pe perechi."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations


@dataclass
class GroupingScore:
    precision: float
    recall: float
    f1: float
    true_pairs: int
    found_pairs: int
    correct_pairs: int


def _pairs(groups: list[list[str]], ignore: set[str]) -> set[tuple[str, str]]:
    out = set()
    for g in groups:
        ids = sorted(p for p in g if p not in ignore)
        out.update(combinations(ids, 2))
    return out


def evaluate(found: list[list[str]], expected: dict, with_translations: bool = False) -> GroupingScore:
    """Fără embeddings, traducerile nu se pot găsi: perechile cu ele nu se numără deloc."""
    translations = {p for g in expected["groups"] for p in g["translation_pages"]}
    gold_groups = [g["pages"] + (g["translation_pages"] if with_translations else []) for g in expected["groups"]]
    ignore = set() if with_translations else translations
    gold = _pairs(gold_groups, ignore)
    got = _pairs(found, ignore)
    correct = len(gold & got)
    precision = correct / len(got) if got else 1.0
    recall = correct / len(gold) if gold else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return GroupingScore(round(precision, 4), round(recall, 4), round(f1, 4), len(gold), len(got), correct)
