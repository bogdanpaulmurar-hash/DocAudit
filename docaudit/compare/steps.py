"""Pașii unei pagini și alinierea lor între paginile aceluiași grup.

Un pas = un element de listă. Paginile fără liste numerotate folosesc rândurile
care încep cu „1.”, „2)” etc.; dacă nici acelea nu există, pagina nu are pași.

Pentru aliniere, valorile (cifre, căi, adrese, coduri) se înlocuiesc cu „<v>”,
ca „Setează portul 443” și „Configurează portul 8443” să fie recunoscute ca
același pas. Reformulările (alt verb) schimbă puțin scorul.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ..group.text import normalize
from ..model import Page

_NUMBERED = re.compile(r"^\s*(\d{1,3})[.)]\s+(.*\S)\s*$")
_STRIP = "\"'„“”«»‚‘’()[]{},;:!?"
_VALUE = re.compile(r"[\d\\/@]|\w\.\w|^-\w|^\w[^A-Z]*[A-Z]")

STEP_MATCH_MIN = 0.5  # sub acest scor doi pași nu sunt „același pas”


def extract_steps(page: Page) -> list[str]:
    steps = [b.text for b in page.blocks if b.type == "list_item" and b.text.strip()]
    if steps:
        return steps
    numbered = [m.group(2) for line in page.text.splitlines() if (m := _NUMBERED.match(line))]
    return numbered


def tokens(text: str) -> list[str]:
    """Cuvintele pasului, fără punctuația de la capete (valorile rămân întregi: \\\\srv\\x, 5.2)."""
    out = []
    for raw in text.split():
        tok = raw.strip(_STRIP).rstrip(".")
        if tok:
            out.append(tok)
    return out


def is_value(tok: str) -> bool:
    """Arată ca o valoare de configurare: cifre, căi, adrese, opțiuni de comandă, coduri (GRP-Users)."""
    return bool(_VALUE.search(tok))


def values_of(text: str) -> tuple[str, ...]:
    return tuple(t for t in tokens(text) if is_value(t))


def masked(text: str) -> list[str]:
    out = []
    for t in tokens(text):
        if is_value(t):
            if not out or out[-1] != "<v>":
                out.append("<v>")
        else:
            out.extend(normalize(t).split())
    return out


def step_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, masked(a), masked(b), autojunk=False).ratio()


@dataclass
class StepRow:
    """Un pas „comun” al grupului și textul lui pe fiecare pagină care îl are."""

    texts: dict[str, str] = field(default_factory=dict)  # pagină -> textul pasului
    positions: dict[str, int] = field(default_factory=dict)  # pagină -> indexul pasului (de la 0)


def align(steps_by_page: dict[str, list[str]], order: list[str]) -> list[StepRow]:
    """Aliniază pașii paginilor. `order` = paginile în ordinea în care se adaugă (prima = ancora)."""
    rows: list[StepRow] = []
    for pid in order:
        steps = steps_by_page.get(pid, [])
        candidates = []
        for si, text in enumerate(steps):
            for ri, row in enumerate(rows):
                score = max(step_similarity(text, other) for other in row.texts.values())
                if score >= STEP_MATCH_MIN:
                    candidates.append((score, -abs(si - _mean_pos(row)), si, ri))
        used_steps, used_rows = set(), set()
        for _, _, si, ri in sorted(candidates, reverse=True):
            if si in used_steps or ri in used_rows:
                continue
            rows[ri].texts[pid] = steps[si]
            rows[ri].positions[pid] = si
            used_steps.add(si)
            used_rows.add(ri)
        for si, text in enumerate(steps):
            if si not in used_steps:
                rows.append(StepRow({pid: text}, {pid: si}))
    rows.sort(key=_mean_pos)
    return rows


def _mean_pos(row: StepRow) -> float:
    return sum(row.positions.values()) / len(row.positions)


def out_of_order(sequence: list[int]) -> list[int]:
    """Indicii (din `sequence`) care nu fac parte din cel mai lung subșir crescător."""
    n = len(sequence)
    if n < 2:
        return []
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if sequence[j] < sequence[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    end = max(range(n), key=lambda i: best[i])
    keep = set()
    while end != -1:
        keep.add(end)
        end = prev[end]
    return [i for i in range(n) if i not in keep]
