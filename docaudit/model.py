"""Formatul normalizat DocAudit (schema v1).

Orice sursă (COM OneNote, exporturi manuale, Graph) produce același folder:

    <folder>/
      manifest.json        schema_version, sursa, data extragerii, notebook-uri, selecția
      pages.jsonl          o pagină pe linie
      images/<sha256>.<ext> imaginile, deduplicate după hash (png, jpg, gif...)

Analiza citește doar acest format, deci nu depinde de sursă.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MANIFEST_FILE = "manifest.json"
PAGES_FILE = "pages.jsonl"
IMAGES_DIR = "images"

BLOCK_TYPES = ("heading", "para", "list_item", "table_row")
SOURCE_KINDS = ("onenote_com", "file_export", "graph", "sample")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class Block:
    type: str
    text: str
    level: int = 0


@dataclass
class ImageRef:
    sha256: str
    phash: str | None = None
    alt: str = ""
    ocr_text: str | None = None


@dataclass
class Attachment:
    name: str
    sha256: str


@dataclass
class Source:
    kind: str
    ref: str = ""


@dataclass
class Page:
    id: str
    notebook: str
    section_path: list[str]
    title: str
    created: str
    modified: str
    text: str
    blocks: list[Block] = field(default_factory=list)
    images: list[ImageRef] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    author: str | None = None
    source: Source = field(default_factory=lambda: Source(kind="sample"))
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Page":
        return cls(
            id=d["id"],
            notebook=d["notebook"],
            section_path=list(d["section_path"]),
            title=d["title"],
            created=d["created"],
            modified=d["modified"],
            text=d["text"],
            blocks=[Block(**b) for b in d.get("blocks", [])],
            images=[ImageRef(**i) for i in d.get("images", [])],
            attachments=[Attachment(**a) for a in d.get("attachments", [])],
            links=list(d.get("links", [])),
            author=d.get("author"),
            source=Source(**d.get("source", {"kind": "sample"})),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )


@dataclass
class Manifest:
    source: Source
    extracted_at: str
    notebooks: list[dict[str, Any]]
    selection: dict[str, list[str]]
    page_count: int
    schema_version: int = SCHEMA_VERSION
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Manifest":
        return cls(
            source=Source(**d["source"]),
            extracted_at=d["extracted_at"],
            notebooks=list(d["notebooks"]),
            selection=dict(d["selection"]),
            page_count=d["page_count"],
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            note=d.get("note", ""),
        )


# ---------- citire / scriere ----------

def write_dataset(folder: Path, manifest: Manifest, pages: list[Page]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / MANIFEST_FILE).write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    with (folder / PAGES_FILE).open("w", encoding="utf-8", newline="\n") as f:
        for page in pages:
            f.write(json.dumps(page.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def read_manifest(folder: Path) -> Manifest:
    return Manifest.from_dict(json.loads((folder / MANIFEST_FILE).read_text("utf-8")))


def read_pages(folder: Path) -> list[Page]:
    lines = (folder / PAGES_FILE).read_text("utf-8").splitlines()
    return [Page.from_dict(json.loads(line)) for line in lines if line.strip()]


def image_path(folder: Path, sha256: str) -> Path | None:
    """Fișierul imaginii cu acest hash, oricare ar fi extensia; None dacă lipsește."""
    matches = sorted((folder / IMAGES_DIR).glob(f"{sha256}.*"))
    return matches[0] if matches else None


# ---------- validare ----------

def _is_iso(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_page_dict(d: dict[str, Any]) -> list[str]:
    """Problemele unei pagini, ca text. Listă goală = pagină validă."""
    errors: list[str] = []
    pid = d.get("id", "?")

    def err(msg: str) -> None:
        errors.append(f"{pid}: {msg}")

    if d.get("schema_version") != SCHEMA_VERSION:
        err(f"schema_version {d.get('schema_version')!r}, așteptat {SCHEMA_VERSION}")
    for key in ("id", "notebook", "title", "text"):
        if not isinstance(d.get(key), str) or (key != "text" and not d.get(key)):
            err(f"câmpul '{key}' lipsește sau nu e text")
    sp = d.get("section_path")
    if not isinstance(sp, list) or not sp or not all(isinstance(s, str) and s for s in sp):
        err("'section_path' trebuie să fie o listă nevidă de nume")
    for key in ("created", "modified"):
        if not _is_iso(d.get(key)):
            err(f"'{key}' nu e dată ISO 8601")
    if _is_iso(d.get("created")) and _is_iso(d.get("modified")) and d["modified"] < d["created"]:
        err("'modified' e înainte de 'created'")
    for i, b in enumerate(d.get("blocks", [])):
        if b.get("type") not in BLOCK_TYPES:
            err(f"blocul {i} are tip necunoscut {b.get('type')!r}")
    for i, img in enumerate(d.get("images", [])):
        if not _SHA256.match(str(img.get("sha256", ""))):
            err(f"imaginea {i} nu are sha256 valid")
    kind = d.get("source", {}).get("kind")
    if kind not in SOURCE_KINDS:
        err(f"sursă necunoscută {kind!r}")
    return errors


def validate_dataset(folder: Path) -> list[str]:
    """Verifică tot folderul: manifest, pagini, imagini. Nu scrie nimic."""
    errors: list[str] = []
    mpath, ppath = folder / MANIFEST_FILE, folder / PAGES_FILE
    if not mpath.is_file():
        return [f"lipsește {MANIFEST_FILE}"]
    if not ppath.is_file():
        return [f"lipsește {PAGES_FILE}"]

    manifest = json.loads(mpath.read_text("utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"manifest: schema_version {manifest.get('schema_version')!r}, așteptat {SCHEMA_VERSION}")

    seen: set[str] = set()
    count = 0
    for n, line in enumerate(ppath.read_text("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"{PAGES_FILE} rândul {n}: JSON invalid ({e.msg})")
            continue
        count += 1
        errors.extend(validate_page_dict(d))
        pid = d.get("id")
        if pid in seen:
            errors.append(f"{pid}: id duplicat")
        seen.add(pid)
        for img in d.get("images", []):
            sha = img.get("sha256", "")
            if _SHA256.match(str(sha)) and image_path(folder, sha) is None:
                errors.append(f"{pid}: imaginea {sha[:12]}… lipsește din {IMAGES_DIR}/")

    if manifest.get("page_count") != count:
        errors.append(f"manifest: page_count {manifest.get('page_count')} dar {PAGES_FILE} are {count} pagini")
    return errors
