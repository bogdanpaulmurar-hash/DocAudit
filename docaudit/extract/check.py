"""Compară o extragere cu eșantionul fictiv (pentru notebook-ul de test pe Windows).

Paginile se potrivesc după titlu. Se verifică textul, blocurile, locul
(notebook-ul original devine grup de secțiuni în notebook-ul de test) și
numărul de imaginilor. Datele nu se compară: OneNote pune data creării la
import, nu pe cea din eșantion.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Page, read_pages
from ..sample import build_sample


def compare_pages(extracted: list[Page], expected: list[Page]) -> list[str]:
    problems: list[str] = []
    by_title = {p.title: p for p in extracted}
    for exp in expected:
        got = by_title.pop(exp.title, None)
        if got is None:
            problems.append(f"lipsește pagina „{exp.title}”")
            continue
        # în notebook-ul de test, notebook-ul original devine grup de secțiuni
        nested = got.notebook != exp.notebook
        where = [exp.notebook, *exp.section_path] if nested else exp.section_path
        if got.section_path[-len(where):] != where:
            problems.append(f"„{exp.title}”: secțiunea {got.section_path} în loc de {where}")
        if got.text != exp.text:
            problems.append(f"„{exp.title}”: textul diferă")
        if [(b.type, b.text) for b in got.blocks] != [(b.type, b.text) for b in exp.blocks]:
            problems.append(f"„{exp.title}”: blocurile diferă")
        if len(got.images) != len(exp.images):
            problems.append(f"„{exp.title}”: {len(got.images)} imagini în loc de {len(exp.images)}")
    for title in by_title:
        problems.append(f"pagină în plus: „{title}”")
    return problems


def compare_to_sample(folder: Path) -> list[str]:
    _, expected, _, _ = build_sample()
    return compare_pages(read_pages(folder), expected)
