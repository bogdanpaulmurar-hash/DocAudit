"""Transformări pe XML-ul unei pagini OneNote, pentru arhivare, marcare și restaurare.

Nu ating OneNote: primesc și întorc text XML. Le folosesc atât scriitorul COM,
cât și OneNote-ul fals din teste.
"""

from __future__ import annotations

import html
import xml.etree.ElementTree as ET

from ..extract.htmltext import inline_html
from ..extract.onenote_xml import NS, ONE

# Atribute pe care OneNote le dă la citire, dar le refuză (sau le încurcă) pe o pagină nouă.
_DROP_ATTRS = ("objectID", "lastModifiedTime", "creationTime", "author", "authorInitials",
               "authorResolutionID", "lastModifiedBy", "lastModifiedByInitials",
               "lastModifiedByResolutionID", "selected", "isCurrentlyViewed", "lang")


def _parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def _tostring(root: ET.Element) -> str:
    ET.register_namespace("one", NS)
    return ET.tostring(root, encoding="unicode")


def page_id_of(xml: str) -> str:
    return _parse(xml).get("ID", "")


def title_of(xml: str) -> str:
    """Titlul paginii ca text simplu (fără HTML-ul din one:T)."""
    root = _parse(xml)
    t = root.find(f"{ONE}Title//{ONE}T")
    if t is None or t.text is None:
        return root.get("name", "")
    return inline_html(t.text)[0]


def copy_page_xml(xml: str, new_page_id: str, note: str | None = None) -> str:
    """Conținutul paginii, gata de scris într-o pagină nouă (alt ID), cu o notă opțională la început."""
    root = _parse(xml)
    root.set("ID", new_page_id)
    for a in ("lastModifiedTime", "isCurrentlyViewed", "selected"):
        root.attrib.pop(a, None)
    for el in root.iter():
        if el is root:
            continue
        for a in _DROP_ATTRS:
            el.attrib.pop(a, None)
        if el.tag == f"{ONE}Image" and el.find(f"{ONE}Data") is not None:
            el.attrib.pop("callbackID", None)  # imaginea vine chiar în XML (base64)
    if note:
        _prepend_note(root, note)
    return _tostring(root)


def _prepend_note(root: ET.Element, note: str) -> None:
    outline = root.find(f"{ONE}Outline")
    if outline is None:
        outline = ET.Element(f"{ONE}Outline")
        children = list(root)
        title_at = next((i for i, c in enumerate(children) if c.tag == f"{ONE}Title"), -1)
        root.insert(title_at + 1, outline)
    oec = outline.find(f"{ONE}OEChildren")
    if oec is None:
        oec = ET.SubElement(outline, f"{ONE}OEChildren")
    oe = ET.Element(f"{ONE}OE")
    ET.SubElement(oe, f"{ONE}T").text = f"<i>{html.escape(note, quote=False)}</i>"
    oec.insert(0, oe)


def title_update_xml(xml: str, new_title_html: str) -> tuple[str, str]:
    """XML parțial care schimbă doar titlul paginii. Întoarce (xml, titlul vechi ca HTML din one:T)."""
    root = _parse(xml)
    title = root.find(f"{ONE}Title")
    if title is None:
        raise ValueError("pagina nu are titlu")
    oe = title.find(f"{ONE}OE")
    t = oe.find(f"{ONE}T") if oe is not None else None
    if oe is None or t is None:
        raise ValueError("pagina nu are titlu")
    old = t.text or ""
    page = ET.Element(f"{ONE}Page", {"ID": root.get("ID", "")})
    new_title = ET.SubElement(page, f"{ONE}Title")
    new_oe = ET.SubElement(new_title, f"{ONE}OE", {k: v for k, v in oe.attrib.items() if k == "objectID"})
    ET.SubElement(new_oe, f"{ONE}T").text = new_title_html
    return _tostring(page), old


def prefixed_title(old_title_html: str, prefix: str) -> str:
    return html.escape(prefix, quote=False) + old_title_html


def has_prefix(old_title_html: str, prefix: str) -> bool:
    return inline_html(old_title_html)[0].startswith(prefix.strip())


def title_html_of(xml: str) -> str:
    """Conținutul brut (HTML) al primului one:T din titlu."""
    return title_update_xml(xml, "")[1]
