"""Link-ul din browser al unui notebook OneNote → notebook-ul din OneNote desktop.

Nu deschide link-ul și nu face niciun apel de rețea: doar îl citește ca text și
îl compară cu ierarhia dată de OneNote desktop (atributul `path` al notebook-urilor
din SharePoint / OneDrive e chiar adresa lor web).

Forme cunoscute:
- `https://firma.sharepoint.com/sites/Echipa/Shared%20Documents/Notebook`
- `https://firma.sharepoint.com/:o:/r/sites/Echipa/Shared%20Documents/Notebook?d=…`
- `https://firma.sharepoint.com/sites/Echipa/_layouts/15/Doc.aspx?sourcedoc={…}&wd=target(Retea.one|…)`
- `https://firma.sharepoint.com/sites/Echipa/_layouts/15/onenote.aspx?id=/sites/Echipa/…/Notebook`
- `onenote:https://…/Notebook/Retea.one#Pagina&section-id={…}&page-id={…}&end`
- `https://d.docs.live.net/<id>/Documents/Notebook` (OneDrive personal)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .onenote_xml import Hierarchy, HNotebook

_SHARE = re.compile(r"^/:o:/[a-z]/", re.IGNORECASE)
_TARGET = re.compile(r"target\(([^|)]*?)\.one\|", re.IGNORECASE)


class LinkError(ValueError):
    """Textul nu e un link https către OneNote."""


@dataclass
class LinkInfo:
    location: str | None  # „gazdă/cale/notebook”, fără .one, cu litere mici; None dacă link-ul nu o conține
    section: str | None  # numele secțiunii (din „Secțiune.one”), dacă apare
    page: str | None  # titlul paginii, dacă apare
    hint: str | None  # un nume de notebook ghicit din parametri (file=…)
    open_url: str | None  # link „onenote:” care deschide notebook-ul în OneNote desktop


@dataclass
class LinkMatch:
    notebook: str
    section: str | None  # „Notebook/Grup/Secțiune”, ca în bife
    how: str  # „path”, „section” sau „name”


def _norm(host: str, path: str) -> str:
    path = unquote(path).replace("\\", "/").rstrip("/")
    return f"{host.lower()}{path}".casefold()


def _split_one(path: str) -> tuple[str, str | None]:
    """„/…/Notebook/Grup/Retea.one” → („/…/Notebook/Grup”, „Retea”)."""
    parts = path.rstrip("/").split("/")
    if parts and parts[-1].lower().endswith(".one"):
        return "/".join(parts[:-1]), parts[-1][:-4]
    return path, None


def parse_link(text: str) -> LinkInfo:
    raw = (text or "").strip().strip('"').strip()
    if raw.lower().startswith("onenote:"):
        raw = raw[len("onenote:"):]
    u = urlsplit(raw)
    if u.scheme.lower() not in ("https", "http") or not u.hostname:
        raise LinkError(raw)
    host = u.hostname
    query = parse_qs(u.query)
    path = unquote(u.path)
    section = page = hint = None

    if "/_layouts/" in path.lower():  # Doc.aspx, onenote.aspx, WopiFrame.aspx
        ident = (query.get("id") or [None])[0]
        path = unquote(ident) if ident and ident.startswith("/") else ""
        m = _TARGET.search(unquote((query.get("wd") or [""])[0]))
        if m:
            section = m.group(1).rsplit("/", 1)[-1] or None
        hint = (query.get("file") or [None])[0]
        if hint and hint.lower().endswith(".one"):
            section = section or hint[:-4]
            hint = None
    elif _SHARE.match(path):
        rest = _SHARE.sub("/", path)
        # /:o:/r/ păstrează calea; /:o:/g/ și /:o:/s/ sunt doar un jeton de partajare
        path = rest if path[5:6].lower() == "r" else ""

    if path:
        path, from_file = _split_one(path)
        section = section or from_file
        if u.fragment:
            page = unquote(u.fragment.split("&", 1)[0]) or None
    location = _norm(host, path) if path else None
    open_url = f"onenote:https://{host}{quote(path.rstrip('/'), safe='/')}" if path else None
    return LinkInfo(location=location, section=section, page=page, hint=hint, open_url=open_url)


def _nb_location(nb: HNotebook) -> str | None:
    if not nb.location.lower().startswith(("https://", "http://")):
        return None
    u = urlsplit(nb.location)
    return _norm(u.hostname or "", u.path)


def _section_of(nb: HNotebook, name: str | None) -> str | None:
    if not name:
        return None
    hits = [s for s in nb.sections if s.path[-1].casefold() == name.casefold()] or [
        s for s in nb.sections if (_split_one(unquote(s.location).replace("\\", "/"))[1] or "").casefold()
        == name.casefold()]
    return "/".join([nb.name, *hits[0].path]) if len(hits) == 1 else None


def match_link(hierarchy: Hierarchy, info: LinkInfo) -> LinkMatch | None:
    """Notebook-ul din OneNote desktop la care duce link-ul, sau None."""
    if info.location:
        best: tuple[int, HNotebook] | None = None
        for nb in hierarchy.notebooks:
            loc = _nb_location(nb)
            if loc and (info.location == loc or info.location.startswith(loc + "/")):
                if best is None or len(loc) > best[0]:
                    best = (len(loc), nb)
        if best:
            nb = best[1]
            return LinkMatch(nb.name, _section_of(nb, info.section), "path")

    names = [n for n in (info.hint, info.location and info.location.rsplit("/", 1)[-1]) if n]
    for name in names:
        hits = [nb for nb in hierarchy.notebooks
                if name.casefold() in {nb.name.casefold(), (_nb_location(nb) or "").rsplit("/", 1)[-1]}]
        if len(hits) == 1:
            return LinkMatch(hits[0].name, _section_of(hits[0], info.section), "name")

    if info.section and not info.location:  # doar pentru link-uri fără cale (Doc.aspx)
        hits = [nb for nb in hierarchy.notebooks if _section_of(nb, info.section)]
        if len(hits) == 1:
            return LinkMatch(hits[0].name, _section_of(hits[0], info.section), "section")
    return None
