"""Măsoară comparația pe eșantion (expected.json): conflicte, pași, duplicate, învechite."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..group.text import normalize


@dataclass
class CompareScore:
    conflicts_planted: int = 0
    conflicts_found: int = 0
    conflict_findings: int = 0
    false_alarms: int = 0
    step_diffs_planted: int = 0
    step_diffs_found: int = 0
    stale_planted: int = 0
    stale_found: int = 0
    stale_extra: int = 0
    duplicates_planted: int = 0
    duplicates_found: int = 0
    missed: list[str] = field(default_factory=list)

    @property
    def conflict_recall(self) -> float:
        return self.conflicts_found / self.conflicts_planted if self.conflicts_planted else 1.0

    @property
    def false_alarm_rate(self) -> float:
        return self.false_alarms / self.conflict_findings if self.conflict_findings else 0.0


def _contains(text: str, value: str) -> bool:
    return f" {normalize(value)} " in f" {normalize(text)} "


def _matches(planted: dict, finding: dict) -> bool:
    """Constatarea arată exact conflictul plantat: aceleași pagini diferite, cu valorile lor."""
    vals = planted["values"]
    majority = Counter(vals.values()).most_common(1)[0][0]
    minority = {p for p, v in vals.items() if v != majority}
    d = finding["details"]
    pages = set(finding["pages"])
    if not minority & pages or not set(d["differing"]) & minority and d["majority"]:
        return False
    common = pages & set(vals)
    if len(common) < 2:
        return False
    return all(_contains(d["texts"][p], vals[p]) for p in common) and any(vals[p] == majority for p in common)


def evaluate_compare(findings: dict, expected: dict) -> CompareScore:
    s = CompareScore()
    all_findings = [f for g in findings["groups"] for f in g["findings"]]
    conflicts = [f for f in all_findings if f["kind"] == "value_conflict"]
    s.conflicts_planted = len(expected["conflicts"])
    s.conflict_findings = len(conflicts)
    used = set()
    for c in expected["conflicts"]:
        hits = [i for i, f in enumerate(conflicts) if _matches(c, f)]
        if hits:
            s.conflicts_found += 1
            used.update(hits)
        else:
            s.missed.append(f"conflict {c['group']}/{c['slot']}")
    s.false_alarms = len(conflicts) - len(used)

    steps = [f for f in all_findings if f["kind"] in ("missing_step", "reordered")]
    s.step_diffs_planted = len(expected["step_diffs"])
    for d in expected["step_diffs"]:
        if any(f["kind"] == d["kind"] and d["page"] in f["pages"] for f in steps):
            s.step_diffs_found += 1
        else:
            s.missed.append(f"{d['kind']} {d['page']}")

    flagged = {f["pages"][0] for f in all_findings if f["kind"] == "stale"}
    s.stale_planted = len(expected["stale"])
    s.stale_found = len(flagged & set(expected["stale"]))
    s.stale_extra = len(flagged - set(expected["stale"]))
    s.missed += [f"stale {p}" for p in sorted(set(expected["stale"]) - flagged)]

    dups = {tuple(f["pages"]) for f in all_findings if f["kind"] == "duplicate"}
    s.duplicates_planted = len(expected["duplicates"])
    s.duplicates_found = sum(tuple(sorted(d)) in dups for d in expected["duplicates"])
    return s
