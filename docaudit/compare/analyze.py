"""Compararea paginilor dintr-un grup: conflicte de valori, pași diferiți, duplicate, învechire.

Totul e doar citire. Rezultatul e o listă de constatări (Finding), fiecare cu dovada
(fragmentele din pagini) și o sugestie de pagină de referință. Nimic nu se aplică singur.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from difflib import SequenceMatcher

from ..group.text import normalize
from ..lang import detect_language, stale_markers_in
from ..model import Page
from .steps import StepRow, align, extract_steps, out_of_order, tokens, values_of

KINDS = ("value_conflict", "missing_step", "extra_step", "reordered", "duplicate", "stale", "shared_image")
SEVERITIES = ("high", "medium", "low")


@dataclass
class CompareSettings:
    duplicate_min: float = 0.9  # asemănarea textului (fără valori schimbate) de la care e duplicat
    stale_age_days: int = 3 * 365  # cu cât e mai veche decât cea mai nouă pagină din grup
    conflict_age_days: int = 365  # pagină în minoritate la un conflict și mai veche cu atât
    stale_markers: bool = True


@dataclass
class Finding:
    kind: str
    severity: str
    group: str
    pages: list[str]
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GroupReport:
    group: str
    pages: list[str]
    reference: str | None  # pagina care pare versiunea curentă (doar sugestie)
    other_language: list[str]  # pagini în altă limbă: nu se compară pas cu pas
    findings: list[Finding]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["findings"] = [f.to_dict() for f in self.findings]
        return d


def _date(page: Page) -> datetime:
    try:
        return datetime.fromisoformat(page.modified.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


_VERSION = re.compile(r"(?:^|[^\w.])v?(\d+(?:\.\d+)+)|_v(\d+)|\bv(\d+)\b", re.IGNORECASE)


def _version(value: str) -> tuple[int, ...] | None:
    m = _VERSION.search(value)
    if not m:
        return None
    raw = next(g for g in m.groups() if g)
    return tuple(int(x) for x in raw.split("."))


def _fragment(text: str, reference: str) -> str:
    """Partea din `text` care diferă de `reference` (cuvinte întregi), cu valorile ei."""
    a, b = tokens(text), tokens(reference)
    na, nb = [normalize(t) for t in a], [normalize(t) for t in b]
    theirs = set(values_of(reference))
    parts = []
    for op, i1, i2, _, _ in SequenceMatcher(None, na, nb, autojunk=False).get_opcodes():
        # doar porțiunile cu o valoare care lipsește din cealaltă pagină (nu verbele reformulate)
        if op != "equal" and any(v not in theirs for t in a[i1:i2] for v in values_of(t)):
            parts.append(" ".join(a[i1:i2]))
    return " … ".join(parts) or " ".join(v for v in values_of(text) if v not in theirs)


def _majority(values: dict[str, tuple[str, ...]]) -> tuple[str, ...] | None:
    counts = Counter(values.values())
    (top, n), *rest = counts.most_common()
    if rest and rest[0][1] == n:
        return None  # egalitate: nu există o majoritate
    return top


def _conflicts(group: str, rows: list[StepRow], dates: dict[str, datetime]) -> list[Finding]:
    out = []
    for ri, row in enumerate(rows):
        if len(row.texts) < 2:
            continue
        vals = {pid: values_of(text) for pid, text in row.texts.items()}
        if len(set(vals.values())) < 2:
            continue
        major = _majority(vals)
        ref_pid = next((p for p in sorted(vals, key=lambda p: dates[p], reverse=True) if vals[p] == major), None)
        if ref_pid is None:  # fără majoritate: comparăm cu pagina cea mai nouă
            ref_pid = max(vals, key=lambda p: dates[p])
        differing = sorted(p for p in vals if vals[p] != vals[ref_pid])
        values = {}
        for pid in sorted(row.texts):
            other = differing[0] if vals[pid] == vals[ref_pid] else ref_pid
            values[pid] = _fragment(row.texts[pid], row.texts[other])
        out.append(Finding(
            kind="value_conflict", severity="high", group=group, pages=sorted(row.texts),
            details={"step": ri, "differing": differing, "majority": major is not None,
                     "values": values, "texts": dict(sorted(row.texts.items()))},
        ))
    return out


def _step_diffs(group: str, rows: list[StepRow], pids: list[str], dates: dict[str, datetime]) -> list[Finding]:
    out = []
    with_steps = [p for p in pids if any(p in r.texts for r in rows)]
    if len(with_steps) < 2:
        return out
    for ri, row in enumerate(rows):
        present = [p for p in with_steps if p in row.texts]
        absent = [p for p in with_steps if p not in row.texts]
        if not absent:
            continue
        sample_text = row.texts[max(present, key=lambda p: dates[p])]
        if len(present) >= len(absent):
            out.append(Finding("missing_step", "medium", group, sorted(absent),
                               {"step": ri, "text": sample_text, "present_in": sorted(present)}))
        else:
            out.append(Finding("extra_step", "low", group, sorted(present),
                               {"step": ri, "text": sample_text, "absent_in": sorted(absent)}))
    # ordinea: fiecare pagină față de ordinea comună (rândurile sunt sortate după poziția medie)
    for pid in with_steps:
        seq = [(row.positions[pid], ri) for ri, row in enumerate(rows) if pid in row.positions]
        order = [ri for _, ri in sorted(seq)]
        bad = out_of_order(order)
        if bad:
            moved = sorted(order[i] for i in bad)
            others = [p for p in with_steps if p != pid]
            # cu două pagini nu se poate spune care e „greșită”: le numim pe amândouă
            pages = sorted([pid] + others) if len(with_steps) == 2 else [pid]
            out.append(Finding("reordered", "medium", group, pages,
                               {"page": pid, "steps": moved, "texts": [rows[r].texts[pid] for r in moved]}))
            if len(with_steps) == 2:
                break
    return out


def _duplicates(group: str, pages: list[Page], settings: CompareSettings) -> list[Finding]:
    out = []
    norm = {p.id: normalize(p.text).split() for p in pages}
    for i, a in enumerate(pages):
        for b in pages[i + 1:]:
            score = SequenceMatcher(None, norm[a.id], norm[b.id], autojunk=False).ratio()
            if score >= settings.duplicate_min:
                older, newer = sorted([a, b], key=_date)
                out.append(Finding("duplicate", "low", group, sorted([a.id, b.id]),
                                   {"similarity": round(score, 3), "older": older.id, "newer": newer.id}))
    return out


def _stale(group: str, pages: list[Page], conflicts: list[Finding], settings: CompareSettings) -> list[Finding]:
    dates = {p.id: _date(p) for p in pages}
    newest = max(dates.values())
    out = []
    for p in pages:
        reasons: list[dict] = []
        if settings.stale_markers:
            found = stale_markers_in(f"{p.title}\n{p.text}")
            if found:
                reasons.append({"reason": "marker", "markers": found})
        for c in conflicts:
            if p.id not in c.details["differing"] or not c.details["majority"]:
                continue
            others = [q for q in c.pages if q not in c.details["differing"]]
            mine, theirs = _version(c.details["values"][p.id]), _version(c.details["values"][others[0]])
            if mine and theirs and mine < theirs:
                reasons.append({"reason": "lower_version", "value": c.details["values"][p.id],
                                "other": c.details["values"][others[0]]})
            elif all((dates[q] - dates[p.id]).days >= settings.conflict_age_days for q in others):
                reasons.append({"reason": "old_minority_value", "value": c.details["values"][p.id]})
        age = (newest - dates[p.id]).days
        if len(pages) > 1 and age >= settings.stale_age_days and dates[p.id] == min(dates.values()):
            reasons.append({"reason": "old", "days_older": age})
        if reasons:
            strong = any(r["reason"] in ("marker", "lower_version") for r in reasons) or len(reasons) > 1
            out.append(Finding("stale", "high" if strong else "medium", group, [p.id],
                               {"reasons": reasons, "modified": p.modified}))
    return out


def compare_group(group: str, pages: list[Page], settings: CompareSettings | None = None) -> GroupReport:
    settings = settings or CompareSettings()
    dates = {p.id: _date(p) for p in pages}
    langs = {p.id: detect_language(p.text) for p in pages}
    counted = Counter(v for v in langs.values() if v)
    main_lang = counted.most_common(1)[0][0] if counted else None
    other_language = sorted(pid for pid, lg in langs.items() if main_lang and lg and lg != main_lang)
    same = [p for p in pages if p.id not in other_language]

    # ancora = pagina cu cei mai mulți pași, apoi cea mai nouă
    steps = {p.id: extract_steps(p) for p in same}
    order = sorted(steps, key=lambda pid: (-len(steps[pid]), -dates[pid].timestamp(), pid))
    rows = align(steps, order)

    conflicts = _conflicts(group, rows, dates)
    findings = conflicts + _step_diffs(group, rows, order, dates) + _duplicates(group, same, settings)
    stale = _stale(group, pages, conflicts, settings)
    findings += stale

    stale_ids = {f.pages[0] for f in stale}
    agree = Counter()
    for c in conflicts:
        for pid in c.pages:
            agree[pid] += 0 if pid in c.details["differing"] and c.details["majority"] else 1
    candidates = [p for p in same if p.id not in stale_ids] or same
    reference = max(candidates, key=lambda p: (agree[p.id], dates[p.id])).id if candidates else None
    return GroupReport(group, sorted(p.id for p in pages), reference, other_language, findings)


def shared_images(pages: list[Page]) -> list[Finding]:
    """Aceeași imagine (după hash) pe mai multe pagini, din orice grup."""
    by_sha: dict[str, set[str]] = {}
    for p in pages:
        for img in p.images:
            by_sha.setdefault(img.sha256, set()).add(p.id)
    return [Finding("shared_image", "low", "", sorted(ids), {"sha256": sha})
            for sha, ids in sorted(by_sha.items()) if len(ids) > 1]
