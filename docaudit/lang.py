"""Ajutoare pentru documentație amestecată în română, engleză și germană.

- detect_language(): ghicește limba unei pagini după cuvinte frecvente (fără biblioteci).
- STALE_MARKERS: expresii care arată că o pagină e învechită, în cele trei limbi
  (folosite la compararea din Etapa 5; se pot extinde din setări).
"""

from __future__ import annotations

from .group.text import normalize

LANGUAGES = ("ro", "en", "de")

_COMMON = {
    "ro": {"si", "de", "la", "in", "cu", "pe", "nu", "care", "este", "sau", "pentru", "dupa", "din", "se", "un", "o"},
    "en": {"the", "and", "to", "of", "in", "on", "for", "with", "is", "your", "you", "after", "from", "a", "an"},
    "de": {"der", "die", "das", "und", "zu", "mit", "ist", "nicht", "fur", "den", "auf", "im", "ein", "eine", "nach"},
}

STALE_MARKERS = {
    "ro": ("nu mai folositi", "nu mai folosiți", "varianta veche", "procedura veche", "invechit", "învechit",
           "depasit", "depășit", "inlocuit de", "înlocuit de"),
    "en": ("deprecated", "obsolete", "do not use", "no longer used", "outdated", "superseded by", "legacy"),
    "de": ("veraltet", "nicht mehr verwenden", "nicht mehr gultig", "nicht mehr gültig", "ersetzt durch",
           "obsolet", "alte version"),
}


def detect_language(text: str) -> str | None:
    """„ro”, „en”, „de” sau None dacă textul e prea scurt ca să se poată spune."""
    words = normalize(text).split()
    if len(words) < 4:
        return None
    counts = {lang: sum(w in common for w in words) for lang, common in _COMMON.items()}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] >= 2 else None


def stale_markers_in(text: str) -> list[str]:
    """Expresiile de „pagină învechită” găsite în text, în oricare din limbi."""
    norm = f" {normalize(text)} "
    found = []
    for markers in STALE_MARKERS.values():
        for m in markers:
            nm = normalize(m)
            if f" {nm} " in norm and nm not in found:
                found.append(nm)
    return found
