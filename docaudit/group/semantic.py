"""Asemănare după sens, cu un model de embeddings rulat local (opțional).

Prinde traduceri RO↔EN și reformulări. Necesită `pip install sentence-transformers`
și modelul descărcat o singură dată; după aceea rulează offline (rețeaua e
interzisă explicit la încărcare). Fără ele, DocAudit grupează doar după text și titlu.
"""

from __future__ import annotations

import os

from ..model import Page
from .similarity import page_body

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


class SemanticUnavailable(RuntimeError):
    """Modelul de embeddings nu e instalat sau nu e descărcat local."""


def semantic_scores(pages: list[Page], model_name: str = DEFAULT_MODEL,
                    min_value: float = 0.5) -> dict[tuple[int, int], float]:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except ImportError as e:
        raise SemanticUnavailable("sentence-transformers nu e instalat") from e
    try:
        model = SentenceTransformer(model_name, local_files_only=True)
    except Exception as e:
        raise SemanticUnavailable(f"modelul {model_name} nu e descărcat local") from e
    texts = [f"{p.title}\n{page_body(p)}"[:2000] for p in pages]
    emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    sims = emb @ emb.T
    out = {}
    n = len(pages)
    for i in range(n):
        for j in range(i + 1, n):
            s = float(sims[i, j])
            if s >= min_value:
                out[(i, j)] = s
    return out


def download_model(model_name: str = DEFAULT_MODEL) -> str:
    """Singurul loc care folosește internetul: descarcă modelul o dată, în cache-ul local."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except ImportError as e:
        raise SemanticUnavailable("sentence-transformers nu e instalat") from e
    for var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        os.environ.pop(var, None)
    SentenceTransformer(model_name)
    return model_name
