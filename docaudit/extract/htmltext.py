"""Text simplu și linkuri din fragmente HTML (textul OneNote și exporturile .mht)."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_SPACES = re.compile(r"[ \t ]+")


class _InlineText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.parts.append(" ")
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean(text: str) -> str:
    return _SPACES.sub(" ", text.replace("\r", " ").replace("\n", " ")).strip()


def inline_html(fragment: str) -> tuple[str, list[str]]:
    """Textul vizibil dintr-un fragment HTML de un rând, plus linkurile lui."""
    p = _InlineText()
    p.feed(fragment)
    p.close()
    return clean("".join(p.parts)), p.links
