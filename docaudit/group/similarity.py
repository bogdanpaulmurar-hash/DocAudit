"""Scorul de asemănare între pagini: text + titlu (+ sens, opțional).

Perechile candidate se găsesc printr-un index inversat, deci nu se compară
fiecare pagină cu fiecare: merge și pe mii de pagini.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..model import Page
from .text import DEFAULT_TITLE_NOISE, Vector, char_ngrams, clean_title, normalize, tfidf


@dataclass
class SimilaritySettings:
    text_weight: float = 0.7
    title_weight: float = 0.3
    semantic_floor: float = 0.5  # cu embeddings: sub această asemănare de sens nu contează
    ngram: int = 4
    title_ngram: int = 3
    max_df: float = 0.3  # n-gramele din >30% din pagini nu ajută
    min_candidate: float = 0.15  # sub acest scor parțial, perechea nu se mai calculează
    title_noise: tuple[str, ...] = DEFAULT_TITLE_NOISE


@dataclass
class PairScore:
    a: str
    b: str
    score: float
    text: float
    title: float
    semantic: float = 0.0


def page_body(p: Page) -> str:
    return "\n".join(b.text for b in p.blocks) or p.text


def _cosines(vectors: list[Vector], min_value: float) -> dict[tuple[int, int], float]:
    index: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for i, v in enumerate(vectors):
        for t, x in v.items():
            index[t].append((i, x))
    result: dict[tuple[int, int], float] = {}
    for i, v in enumerate(vectors):
        acc: dict[int, float] = defaultdict(float)
        for t, x in v.items():
            for j, y in index[t]:
                if j > i:
                    acc[j] += x * y
        for j, s in acc.items():
            if s >= min_value:
                result[(i, j)] = s
    return result


def score_pairs(pages: list[Page], s: SimilaritySettings | None = None,
                semantic: dict[tuple[int, int], float] | None = None) -> list[PairScore]:
    s = s or SimilaritySettings()
    texts = tfidf([char_ngrams(normalize(page_body(p)), s.ngram) for p in pages], s.max_df)
    titles = tfidf([char_ngrams(clean_title(p.title, s.title_noise), s.title_ngram) for p in pages])
    text_cos = _cosines(texts, s.min_candidate)
    title_cos = _cosines(titles, s.min_candidate)
    sem = semantic or {}
    pairs = []
    for key in set(text_cos) | set(title_cos) | set(sem):
        t, ti, se = text_cos.get(key, 0.0), title_cos.get(key, 0.0), sem.get(key, 0.0)
        score = (s.text_weight * t + s.title_weight * ti) / (s.text_weight + s.title_weight)
        if se > s.semantic_floor:
            # sensul poate doar ridica scorul (ex. traduceri), niciodată coborî
            score = max(score, (se - s.semantic_floor) / (1 - s.semantic_floor))
        i, j = key
        pairs.append(PairScore(pages[i].id, pages[j].id, round(score, 4), round(t, 4), round(ti, 4), round(se, 4)))
    pairs.sort(key=lambda p: (-p.score, p.a, p.b))
    return pairs
