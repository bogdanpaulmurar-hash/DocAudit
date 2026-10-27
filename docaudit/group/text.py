"""Pregătirea textului pentru comparare: normalizare și vectori TF-IDF pe n-grame de caractere.

N-gramele de caractere merg bine pe română și engleză amestecate, cu sau fără
diacritice, și pe variații mici de formulare. Totul e local, fără biblioteci externe.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

_NON_ALNUM = re.compile(r"[^0-9a-z]+")

# cuvinte din titluri care nu spun nimic despre procedură (se pot schimba din setări)
DEFAULT_TITLE_NOISE = (
    "ghid", "actualizat", "nou", "noua", "vechi", "veche", "copie", "pe pasi", "pasi",
    "procedura", "draft", "final", "v2", "update", "updated", "copy", "new", "old",
)

Vector = dict[str, float]


def normalize(text: str) -> str:
    """minuscule, fără diacritice, doar litere și cifre separate de un spațiu."""
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _NON_ALNUM.sub(" ", text).strip()


def clean_title(title: str, noise: tuple[str, ...] = DEFAULT_TITLE_NOISE) -> str:
    t = f" {normalize(title)} "
    for word in sorted(noise, key=len, reverse=True):
        t = t.replace(f" {normalize(word)} ", " ")
    return " ".join(t.split())


def char_ngrams(text: str, n: int) -> Counter[str]:
    grams: Counter[str] = Counter()
    for word in text.split():
        w = f" {word} "
        if len(w) <= n:
            grams[w] += 1
            continue
        for i in range(len(w) - n + 1):
            grams[w[i : i + n]] += 1
    return grams


def tfidf(docs: list[Counter[str]], max_df: float = 1.0) -> list[Vector]:
    """Vectori TF-IDF normalizați (lungime 1). Termenii prea frecvenți se ignoră."""
    n = len(docs)
    df: Counter[str] = Counter()
    for d in docs:
        df.update(d.keys())
    limit = max(1, int(max_df * n))
    idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items() if c <= limit}
    vectors = []
    for d in docs:
        v = {t: (1 + math.log(c)) * idf[t] for t, c in d.items() if t in idf}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vectors.append({t: x / norm for t, x in v.items()})
    return vectors
