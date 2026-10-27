"""Citirea (și, pentru teste, scrierea) XML-ului OneNote, schema 2013.

OneNote desktop dă prin COM două tipuri de XML:
- ierarhia (GetHierarchy): notebook-uri → grupuri de secțiuni → secțiuni → pagini;
- conținutul unei pagini (GetPageContent): titlu, contururi cu paragrafe, liste,
  tabele, imagini (base64), fișiere atașate.

Aici le transformăm în formatul normalizat DocAudit (docaudit.model.Page).
Funcțiile render_* produc același XML din pagini existente: le folosesc testele
(dus-întors) și scriptul care creează notebook-ul de test pe Windows.
"""

from __future__ import annotations

import base64
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..model import Attachment, Block, ImageRef, Page, Source
from .htmltext import inline_html

NS = "http://schemas.microsoft.com/office/onenote/2013/onenote"
ONE = f"{{{NS}}}"
ET.register_namespace("one", NS)

RECYCLE_BIN_ATTRS = ("isRecycleBin", "isInRecycleBin", "isDeletedPages")
_HEADING = re.compile(r"^h([1-6])$")
_EXT = re.compile(r"^[a-z0-9]{1,5}$")


# ---------- ierarhia ----------

@dataclass
class HPage:
    id: str
    title: str
    created: str
    modified: str
    notebook: str
    section_path: list[str]
    level: int = 1


@dataclass
class HSection:
    id: str
    notebook: str
    path: list[str]
    pages: list[HPage] = field(default_factory=list)


@dataclass
class HNotebook:
    id: str
    name: str
    sections: list[HSection] = field(default_factory=list)


@dataclass
class Hierarchy:
    notebooks: list[HNotebook]

    def pages(self) -> list[HPage]:
        return [p for nb in self.notebooks for s in nb.sections for p in s.pages]


def normalize_date(value: str | None) -> str:
    """„2025-03-14T09:30:00.000Z” → „2025-03-14T09:30:00Z” (UTC, la secundă)."""
    if not value:
        return "1970-01-01T00:00:00Z"
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _deleted(el: ET.Element) -> bool:
    return any(el.get(a) == "true" for a in RECYCLE_BIN_ATTRS)


def parse_hierarchy(xml: str) -> Hierarchy:
    """Ierarhia completă, fără Coșul de reciclare OneNote."""
    root = ET.fromstring(xml)
    notebooks: list[HNotebook] = []
    for nb_el in root.iter(f"{ONE}Notebook"):
        name = nb_el.get("nickname") or nb_el.get("name") or "?"
        nb = HNotebook(id=nb_el.get("ID", ""), name=name)

        def walk(container: ET.Element, path: list[str]) -> None:
            for child in container:
                if _deleted(child):
                    continue
                if child.tag == f"{ONE}SectionGroup":
                    walk(child, path + [child.get("name", "?")])
                elif child.tag == f"{ONE}Section":
                    sec_path = path + [child.get("name", "?")]
                    sec = HSection(id=child.get("ID", ""), notebook=name, path=sec_path)
                    for p in child.findall(f"{ONE}Page"):
                        if _deleted(p):
                            continue
                        sec.pages.append(HPage(
                            id=p.get("ID", ""), title=p.get("name", ""),
                            created=normalize_date(p.get("dateTime")),
                            modified=normalize_date(p.get("lastModifiedTime") or p.get("dateTime")),
                            notebook=name, section_path=sec_path, level=int(p.get("pageLevel", "1")),
                        ))
                    nb.sections.append(sec)

        walk(nb_el, [])
        notebooks.append(nb)
    return Hierarchy(notebooks)


# ---------- conținutul unei pagini ----------

@dataclass
class ImageData:
    ext: str
    data: bytes


def _t_text(oe: ET.Element) -> tuple[str, list[str]]:
    parts, links = [], []
    for t in oe.findall(f"{ONE}T"):
        text, ls = inline_html(t.text or "")
        if text:
            parts.append(text)
        links.extend(ls)
    return " ".join(parts), links


def _all_text(el: ET.Element) -> str:
    texts = []
    for t in el.iter(f"{ONE}T"):
        text, _ = inline_html(t.text or "")
        if text:
            texts.append(text)
    return " ".join(texts)


def _position(el: ET.Element) -> tuple[float, float]:
    pos = el.find(f"{ONE}Position")
    if pos is None:
        return (0.0, 0.0)
    return (float(pos.get("y", 0)), float(pos.get("x", 0)))


def parse_page(xml: str, notebook: str, section_path: list[str],
               kind: str = "onenote_com") -> tuple[Page, dict[str, ImageData]]:
    """O pagină OneNote → Page + imaginile ei (după hash). Nu scrie nimic."""
    root = ET.fromstring(xml)
    styles = {s.get("index"): s.get("name", "") for s in root.findall(f"{ONE}QuickStyleDef")}
    blocks: list[Block] = []
    lines: list[str] = []
    links: list[str] = []
    images: dict[str, ImageData] = {}
    refs: list[ImageRef] = []

    def add_image(img: ET.Element) -> None:
        data_el = img.find(f"{ONE}Data")
        if data_el is None or not (data_el.text or "").strip():
            return  # fără date binare (ex. cerut fără piBinaryData)
        data = base64.b64decode(data_el.text)
        sha = hashlib.sha256(data).hexdigest()
        ext = (img.get("format") or "bin").lower()
        images[sha] = ImageData(ext if _EXT.match(ext) else "bin", data)
        ocr = img.find(f"{ONE}OCRData/{ONE}OCRText")
        refs.append(ImageRef(sha256=sha, alt=img.get("alt", ""),
                             ocr_text=(ocr.text or None) if ocr is not None else None))

    def walk(children: ET.Element, depth: int) -> None:
        for oe in children.findall(f"{ONE}OE"):
            table = oe.find(f"{ONE}Table")
            if table is not None:
                for row in table.findall(f"{ONE}Row"):
                    cells = [_all_text(c) for c in row.findall(f"{ONE}Cell")]
                    row_text = " | ".join(cells)
                    if row_text.strip(" |"):
                        blocks.append(Block("table_row", row_text, level=depth))
                        lines.append(row_text)
                for img in table.iter(f"{ONE}Image"):
                    add_image(img)
            for img in oe.findall(f"{ONE}Image"):
                add_image(img)
            text, ls = _t_text(oe)
            links.extend(ls)
            if text:
                lst = oe.find(f"{ONE}List")
                m = _HEADING.match(styles.get(oe.get("quickStyleIndex", ""), ""))
                if lst is not None:
                    num = lst.find(f"{ONE}Number")
                    prefix = (num.get("text") or "") if num is not None else "-"
                    blocks.append(Block("list_item", text, level=depth))
                    lines.append(f"{prefix} {text}".strip())
                elif m:
                    blocks.append(Block("heading", text, level=int(m.group(1))))
                    lines.append(text)
                else:
                    blocks.append(Block("para", text))
                    lines.append(text)
            for sub in oe.findall(f"{ONE}OEChildren"):
                walk(sub, depth + 1)

    title_el = root.find(f"{ONE}Title")
    title = _all_text(title_el) if title_el is not None else ""

    # Elementele de pe pagină, în ordinea de citire (de sus în jos, apoi de la stânga).
    items = [el for el in root if el.tag in (f"{ONE}Outline", f"{ONE}Image")]
    for el in sorted(items, key=_position):
        if el.tag == f"{ONE}Image":
            add_image(el)
        else:
            for children in el.findall(f"{ONE}OEChildren"):
                walk(children, 1)

    attachments = []
    for f in root.iter(f"{ONE}InsertedFile"):
        name = f.get("preferredName") or Path(f.get("pathSource", "fisier")).name
        cache = f.get("pathCache")
        sha = ""
        if cache and Path(cache).is_file():
            sha = hashlib.sha256(Path(cache).read_bytes()).hexdigest()
        attachments.append(Attachment(name=name, sha256=sha))

    page = Page(
        id=root.get("ID", ""), notebook=notebook, section_path=list(section_path),
        title=title or root.get("name", ""),
        created=normalize_date(root.get("dateTime")),
        modified=normalize_date(root.get("lastModifiedTime") or root.get("dateTime")),
        text="\n".join(lines), blocks=blocks, images=refs, attachments=attachments,
        links=list(dict.fromkeys(links)), source=Source(kind=kind, ref=root.get("ID", "")),
    )
    return page, images


# ---------- scriere (teste și notebook de test) ----------

def _sub(parent: ET.Element, tag: str, **attrs: str) -> ET.Element:
    return ET.SubElement(parent, f"{ONE}{tag}", {k: v for k, v in attrs.items() if v is not None})


def _t(parent: ET.Element, text: str) -> None:
    _sub(parent, "T").text = html.escape(text, quote=False)


def render_page_xml(page: Page, images: dict[str, ImageData] | None = None,
                    page_id: str | None = None, for_update: bool = False) -> str:
    """Page → XML de pagină OneNote (pentru teste și pentru UpdatePageContent).

    Cu for_update=True, data paginii devine data ultimei modificări din eșantion
    (OneNote nu permite setarea lui lastModifiedTime).
    """
    images = images or {}
    attrs = {"ID": page_id if page_id is not None else page.id, "name": page.title}
    if for_update:
        attrs["dateTime"] = page.modified
    else:
        attrs.update(dateTime=page.created, lastModifiedTime=page.modified)
    root = ET.Element(f"{ONE}Page", attrs)
    for i, name in enumerate(["PageTitle", "p", "h1", "h2", "h3", "h4", "h5", "h6"]):
        _sub(root, "QuickStyleDef", index=str(i), name=name)
    title = _sub(root, "Title")
    _t(_sub(title, "OE"), page.title)
    outline = _sub(root, "Outline")
    _sub(outline, "Position", x="36", y="86", z="0")
    children = _sub(outline, "OEChildren")
    number = 0
    for b in page.blocks:
        oe = _sub(children, "OE")
        if b.type == "heading":
            oe.set("quickStyleIndex", str(1 + max(1, min(b.level, 6))))
            _t(oe, b.text)
        elif b.type == "list_item":
            number += 1
            _sub(_sub(oe, "List"), "Number", numberSequence="0", numberFormat="##.", text=f"{number}.")
            _t(oe, b.text)
        elif b.type == "table_row":
            row = _sub(_sub(oe, "Table"), "Row")
            for cell in b.text.split(" | "):
                _t(_sub(_sub(_sub(row, "Cell"), "OEChildren"), "OE"), cell)
        else:
            oe.set("quickStyleIndex", "1")
            _t(oe, b.text)
        if b.type != "list_item":
            number = 0
    for i, ref in enumerate(page.images):
        img = images.get(ref.sha256)
        if img is None:
            continue
        el = _sub(root, "Image", format=img.ext, alt=ref.alt or None)
        _sub(el, "Position", x="400", y=str(500 + 120 * i), z="1")
        _sub(el, "Data").text = base64.b64encode(img.data).decode("ascii")
    return ET.tostring(root, encoding="unicode")


def render_hierarchy_xml(pages: list[Page]) -> str:
    """Pagini → XML de ierarhie (notebook-uri, grupuri de secțiuni, secțiuni)."""
    root = ET.Element(f"{ONE}Notebooks")
    nbs: dict[str, ET.Element] = {}
    containers: dict[tuple[str, ...], ET.Element] = {}
    for p in pages:
        if p.notebook not in nbs:
            nbs[p.notebook] = _sub(root, "Notebook", name=p.notebook, nickname=p.notebook,
                                   ID=f"nb:{p.notebook}")
        parent = nbs[p.notebook]
        for depth, name in enumerate(p.section_path):
            key = (p.notebook, *p.section_path[: depth + 1])
            if key not in containers:
                last = depth == len(p.section_path) - 1
                containers[key] = _sub(parent, "Section" if last else "SectionGroup",
                                       name=name, ID="sec:" + "/".join(key))
            parent = containers[key]
        _sub(parent, "Page", ID=p.id, name=p.title, dateTime=p.created,
             lastModifiedTime=p.modified, pageLevel="1")
    return ET.tostring(root, encoding="unicode")
