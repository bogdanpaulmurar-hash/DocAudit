"""Formarea grupurilor din perechile cu scor, respectând corecturile utilizatorului.

Perechile se iau de la cea mai asemănătoare în jos; două grupuri se unesc dacă
scorul trece pragul și dacă utilizatorul nu a spus că două pagini din ele nu
țin împreună. Perechile „unite de mână” se aplică primele.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

from .similarity import PairScore


@dataclass
class Group:
    id: str
    label: str
    pages: list[str]
    min_link: float
    avg_score: float
    pairs: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def cluster(page_ids: list[str], pairs: list[PairScore], threshold: float,
            must_link: list[list[str]] | None = None, cannot_link: list[list[str]] | None = None,
            titles: dict[str, str] | None = None) -> tuple[list[Group], list[str]]:
    """Întoarce (grupuri cu ≥2 pagini, pagini rămase singure)."""
    parent = {p: p for p in page_ids}
    members = {p: {p} for p in page_ids}
    cannot = {_key(a, b) for a, b in (cannot_link or []) if a in parent and b in parent}
    link_score: dict[str, float] = {}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str, score: float, forced: bool = False) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if not forced and any(_key(x, y) in cannot for x in members[ra] for y in members[rb]):
            return
        if len(members[ra]) < len(members[rb]):
            ra, rb = rb, ra
        parent[rb] = ra
        members[ra] |= members.pop(rb)
        link_score[ra] = min(link_score.get(ra, 1.0), link_score.pop(rb, 1.0), score)

    for a, b in must_link or []:
        if a in parent and b in parent:
            union(a, b, 1.0, forced=True)
    for p in pairs:  # deja ordonate descrescător
        if p.score < threshold:
            break
        if p.a in parent and p.b in parent:
            union(p.a, p.b, p.score)

    by_pair = {_key(p.a, p.b): p for p in pairs}
    titles = titles or {}
    groups, alone = [], []
    for root, mem in members.items():
        ids = sorted(mem)
        if len(ids) == 1:
            alone.append(ids[0])
            continue
        inner = [by_pair[_key(a, b)] for i, a in enumerate(ids) for b in ids[i + 1:] if _key(a, b) in by_pair]
        avg = sum(p.score for p in inner) / len(inner) if inner else 0.0
        # eticheta: titlul paginii cele mai „centrale” din grup
        centrality = {pid: sum(p.score for p in inner if pid in (p.a, p.b)) for pid in ids}
        medoid = max(ids, key=lambda pid: (centrality[pid], pid))
        groups.append(Group(
            id="g-" + hashlib.sha1(ids[0].encode("utf-8")).hexdigest()[:8],
            label=titles.get(medoid, medoid), pages=ids,
            min_link=round(link_score.get(root, 1.0), 4), avg_score=round(avg, 4),
            pairs=[asdict(p) for p in sorted(inner, key=lambda p: -p.score)],
        ))
    groups.sort(key=lambda g: (-len(g.pages), g.label))
    return groups, sorted(alone)
