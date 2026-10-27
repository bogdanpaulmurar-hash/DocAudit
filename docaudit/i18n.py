"""Texte vizibile utilizatorului, în română și engleză.

Limba vine din variabila DOCAUDIT_LANG (ro implicit). Cheile lipsă cad pe română,
apoi pe cheia însăși, ca o traducere lipsă să nu oprească aplicația.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from importlib import resources

LANGUAGES = ("ro", "en")
DEFAULT_LANG = "ro"


@lru_cache(maxsize=None)
def _load(lang: str) -> dict[str, str]:
    text = resources.files("docaudit").joinpath(f"locales/{lang}.json").read_text("utf-8")
    return json.loads(text)


def current_lang() -> str:
    lang = os.environ.get("DOCAUDIT_LANG", DEFAULT_LANG).lower()
    return lang if lang in LANGUAGES else DEFAULT_LANG


def t(key: str, lang: str | None = None, **params: object) -> str:
    lang = lang or current_lang()
    text = _load(lang).get(key) or _load(DEFAULT_LANG).get(key) or key
    return text.format(**params) if params else text
