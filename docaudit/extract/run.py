"""Extragerea propriu-zisă: OneNote (prin COM sau un înlocuitor) → format normalizat.

Doar citește din OneNote. Scrie numai în folderul de ieșire DocAudit.
La o a doua rulare în același folder, paginile cu aceeași dată de modificare
se refolosesc fără a mai fi cerute din OneNote (incremental).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..model import IMAGES_DIR, PAGES_FILE, Manifest, Page, Source, image_path, read_pages, write_dataset
from .com import OneNoteSource
from .onenote_xml import ImageData, parse_hierarchy, parse_page
from .selection import Selection


@dataclass
class ExtractReport:
    fetched: int = 0
    reused: int = 0
    skipped: int = 0  # nebifate sau excluse
    removed: int = 0  # erau în rularea anterioară, acum lipsesc sau nu mai sunt bifate
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.fetched + self.reused


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_images(out: Path, images: dict[str, ImageData]) -> None:
    folder = out / IMAGES_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for sha, img in images.items():
        if image_path(out, sha) is None:
            (folder / f"{sha}.{img.ext}").write_bytes(img.data)


def remove_orphan_images(out: Path, pages: list[Page]) -> None:
    """Șterge din cache-ul DocAudit (nu din OneNote) imaginile nefolosite."""
    used = {i.sha256 for p in pages for i in p.images}
    folder = out / IMAGES_DIR
    if folder.is_dir():
        for f in folder.iterdir():
            if f.stem not in used:
                f.unlink()


def extract_to_dataset(
    source: OneNoteSource,
    selection: Selection,
    out: Path,
    incremental: bool = True,
    progress: Callable[[int, int, str], None] | None = None,
    source_label: str = "OneNote desktop (COM)",
) -> ExtractReport:
    report = ExtractReport()
    hierarchy = parse_hierarchy(source.get_hierarchy_xml())

    previous: dict[str, Page] = {}
    if incremental and (out / PAGES_FILE).is_file():
        previous = {p.id: p for p in read_pages(out)}

    wanted = []
    for hp in hierarchy.pages():
        if selection.includes(hp.id, hp.notebook, hp.section_path):
            wanted.append(hp)
        else:
            report.skipped += 1

    pages: list[Page] = []
    for n, hp in enumerate(wanted, start=1):
        if progress:
            progress(n, len(wanted), hp.title)
        old = previous.get(hp.id)
        if old and old.modified == hp.modified and all(image_path(out, i.sha256) for i in old.images):
            # pagina nu s-a schimbat; actualizăm doar locul (poate a fost mutată)
            old.notebook, old.section_path = hp.notebook, list(hp.section_path)
            pages.append(old)
            report.reused += 1
            continue
        try:
            page, images = parse_page(source.get_page_xml(hp.id), hp.notebook, hp.section_path)
        except Exception as e:  # o pagină stricată nu oprește restul
            report.errors.append(f"{hp.notebook}/{'/'.join(hp.section_path)}/{hp.title}: {e}")
            continue
        save_images(out, images)
        pages.append(page)
        report.fetched += 1

    report.removed = len(set(previous) - {p.id for p in pages})

    sections: dict[str, set[str]] = {}
    for p in pages:
        sections.setdefault(p.notebook, set()).add("/".join(p.section_path))
    manifest = Manifest(
        source=Source(kind="onenote_com", ref=source_label),
        extracted_at=_now(),
        notebooks=[{"name": nb, "sections": sorted(s)} for nb, s in sorted(sections.items())],
        selection=selection.to_dict(),
        page_count=len(pages),
    )
    write_dataset(out, manifest, pages)
    remove_orphan_images(out, pages)
    return report
