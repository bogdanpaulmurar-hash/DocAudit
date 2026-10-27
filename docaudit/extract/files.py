"""Import din exporturi manuale, când COM nu e disponibil.

Structura așteptată: <rădăcină>/<Notebook>/<Secțiune>[/<Subsecțiune>]/<pagină>.mht|.docx
(fișierele aflate direct în rădăcină intră în notebook-ul cu numele rădăcinii,
secțiunea „Export”). Un fișier = o pagină.

Limite: exporturile nu păstrează datele OneNote, așa că se folosește data
fișierului; titlul vine din document sau din numele fișierului.
"""

from __future__ import annotations

import email
import hashlib
import re
import zipfile
from datetime import datetime, timezone
from email import policy
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from ..model import Block, ImageRef, Manifest, Page, Source, write_dataset
from .htmltext import clean
from .onenote_xml import ImageData
from .run import ExtractReport, remove_orphan_images, save_images
from .selection import Selection

SUPPORTED = (".mht", ".mhtml", ".docx")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_HEADING_STYLE = re.compile(r"(?:heading|titlu|berschrift)\s*([1-6])", re.IGNORECASE)
_IMG_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/bmp": "bmp",
            "image/x-emf": "emf", "image/tiff": "tif"}


class _HtmlBlocks(HTMLParser):
    """HTML de pagină → blocuri (titluri, paragrafe, liste, rânduri de tabel)."""

    BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.links: list[str] = []
        self.title = ""
        self.images: list[str] = []
        self._stack: list[tuple[str, list[str]]] = []
        self._cells: list[str] | None = None
        self._cell: list[str] | None = None
        self._list_depth = 0
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("ul", "ol"):
            self._list_depth += 1
        elif tag == "tr":
            self._cells = []
        elif tag in ("td", "th"):
            self._cell = []
        elif tag == "a" and a.get("href") and not a["href"].startswith("#"):
            self.links.append(a["href"])
        elif tag == "img" and a.get("src"):
            self.images.append(a["src"])
        elif tag == "br":
            self.handle_data(" ")
        if tag in self.BLOCK_TAGS - {"tr"}:
            inherited = tag
            if self._stack:
                parent, parts = self._stack[-1]
                self._emit(parent, parts)  # textul de dinainte de blocul copil
                parts.clear()
                if parent in ("li", "title") or parent.startswith("h"):
                    inherited = parent  # <li><p>…</p></li> rămâne element de listă
            self._stack.append((inherited, []))

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("ul", "ol"):
            self._list_depth = max(0, self._list_depth - 1)
        elif tag in ("td", "th") and self._cell is not None and self._cells is not None:
            self._cells.append(clean("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._cells is not None:
            row = " | ".join(self._cells)
            if row.strip(" |"):
                self.blocks.append(Block("table_row", row, level=1))
            self._cells = None
        if tag in self.BLOCK_TAGS - {"tr"}:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._cell is not None:
            self._cell.append(data)
        elif self._stack:
            self._stack[-1][1].append(data)

    def _flush(self) -> None:
        if self._stack:
            tag, parts = self._stack.pop()
            self._emit(tag, parts)

    def _emit(self, tag: str, parts: list[str]) -> None:
        text = clean("".join(parts))
        if not text:
            return
        if tag == "title":
            self.title = text
        elif tag.startswith("h") and len(tag) == 2:
            self.blocks.append(Block("heading", text, level=int(tag[1])))
        elif tag == "li":
            self.blocks.append(Block("list_item", text, level=max(1, self._list_depth)))
        else:
            self.blocks.append(Block("para", text))


def _lines(blocks: list[Block]) -> str:
    out, n = [], 0
    for b in blocks:
        if b.type == "list_item":
            n += 1
            out.append(f"{n}. {b.text}")
        else:
            n = 0
            out.append(b.text)
    return "\n".join(out)


def read_mht(path: Path) -> tuple[str, list[Block], list[str], dict[str, ImageData]]:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    html_text, images = "", {}
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == "text/html" and not html_text:
            html_text = part.get_content()
        elif ctype.startswith("image/"):
            data = part.get_payload(decode=True) or b""
            if data:
                images[hashlib.sha256(data).hexdigest()] = ImageData(_IMG_EXT.get(ctype, "bin"), data)
    parser = _HtmlBlocks()
    parser.feed(html_text)
    parser.close()
    blocks = [b for b in parser.blocks if b.text != parser.title or b.type != "para"]
    return parser.title, blocks, parser.links, images


def read_docx(path: Path) -> tuple[str, list[Block], list[str], dict[str, ImageData]]:
    blocks: list[Block] = []
    images: dict[str, ImageData] = {}
    title = ""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if "docProps/core.xml" in names:
            core = ET.fromstring(z.read("docProps/core.xml"))
            t = core.find("{http://purl.org/dc/elements/1.1/}title")
            title = clean(t.text or "") if t is not None else ""
        body = ET.fromstring(z.read("word/document.xml")).find(f"{W}body")
        for el in list(body) if body is not None else []:
            if el.tag == f"{W}p":
                text = clean("".join(t.text or "" for t in el.iter(f"{W}t")))
                if not text:
                    continue
                style = el.find(f"{W}pPr/{W}pStyle")
                m = _HEADING_STYLE.search(style.get(f"{W}val", "")) if style is not None else None
                if el.find(f"{W}pPr/{W}numPr") is not None:
                    blocks.append(Block("list_item", text, level=1))
                elif m:
                    blocks.append(Block("heading", text, level=int(m.group(1))))
                elif style is not None and style.get(f"{W}val", "").lower() == "title" and not title:
                    title = text
                else:
                    blocks.append(Block("para", text))
            elif el.tag == f"{W}tbl":
                for tr in el.iter(f"{W}tr"):
                    cells = [clean("".join(t.text or "" for t in tc.iter(f"{W}t"))) for tc in tr.iter(f"{W}tc")]
                    row = " | ".join(cells)
                    if row.strip(" |"):
                        blocks.append(Block("table_row", row, level=1))
        for name in sorted(n for n in names if n.startswith("word/media/")):
            data = z.read(name)
            ext = Path(name).suffix.lstrip(".").lower() or "bin"
            images[hashlib.sha256(data).hexdigest()] = ImageData(ext, data)
    if not title and blocks and blocks[0].type in ("heading", "para"):
        title = blocks.pop(0).text
    return title, blocks, [], images


def _location(root: Path, file: Path) -> tuple[str, list[str]]:
    parts = file.relative_to(root).parts[:-1]
    if not parts:
        return root.name, ["Export"]
    if len(parts) == 1:
        return parts[0], ["Export"]
    return parts[0], list(parts[1:])


def import_files(root: Path, out: Path, selection: Selection | None = None) -> ExtractReport:
    """Importă toate fișierele .mht/.docx de sub root în formatul normalizat."""
    selection = selection or Selection()
    report = ExtractReport()
    pages: list[Page] = []
    for file in sorted(p for p in root.rglob("*") if p.suffix.lower() in SUPPORTED and p.is_file()):
        rel = file.relative_to(root).as_posix()
        page_id = "file:" + hashlib.sha1(rel.encode("utf-8")).hexdigest()[:16]
        notebook, section_path = _location(root, file)
        if not selection.includes(page_id, notebook, section_path):
            report.skipped += 1
            continue
        try:
            reader = read_docx if file.suffix.lower() == ".docx" else read_mht
            title, blocks, links, images = reader(file)
        except Exception as e:
            report.errors.append(f"{rel}: {e}")
            continue
        mtime = datetime.fromtimestamp(file.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        save_images(out, images)
        pages.append(Page(
            id=page_id, notebook=notebook, section_path=section_path, title=title or file.stem,
            created=mtime, modified=mtime, text=_lines(blocks), blocks=blocks,
            images=[ImageRef(sha256=s) for s in images], links=list(dict.fromkeys(links)),
            source=Source(kind="file_export", ref=rel),
        ))
        report.fetched += 1

    sections: dict[str, set[str]] = {}
    for p in pages:
        sections.setdefault(p.notebook, set()).add("/".join(p.section_path))
    manifest = Manifest(
        source=Source(kind="file_export", ref=str(root)),
        extracted_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        notebooks=[{"name": nb, "sections": sorted(s)} for nb, s in sorted(sections.items())],
        selection=selection.to_dict(),
        page_count=len(pages),
        note="Import din fișiere exportate: datele sunt cele ale fișierelor, nu cele din OneNote.",
    )
    write_dataset(out, manifest, pages)
    remove_orphan_images(out, pages)
    return report
