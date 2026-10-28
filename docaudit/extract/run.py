"""Extragerea propriu-zisă: OneNote (prin COM sau un înlocuitor) → format normalizat.

Doar citește din OneNote. Scrie numai în folderul de ieșire DocAudit.
La o a doua rulare în același folder, paginile cu aceeași dată de modificare
se refolosesc fără a mai fi cerute din OneNote (incremental).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .. import log
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
    cancelled: bool = False
    aborted: str = ""  # de ce s-a oprit extragerea înainte de final (aceeași eroare la primele pagini)
    seconds: float = 0.0

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


CHECKPOINT_EVERY = 50  # la notebook-uri mari: ce s-a citit se salvează pe parcurs
ABORT_AFTER = 5  # primele pagini cerute pică toate → oprește, nu mai încerca alte sute


class _Abort(Exception):
    pass


def _write(out: Path, pages: list[Page], selection: Selection, source_label: str) -> None:
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


def extract_to_dataset(
    source: OneNoteSource,
    selection: Selection,
    out: Path,
    incremental: bool = True,
    progress: Callable[[int, int, str], None] | None = None,
    source_label: str = "OneNote desktop (COM)",
    cancel: Callable[[], bool] | None = None,
    checkpoint_every: int = CHECKPOINT_EVERY,
    abort_after: int = ABORT_AFTER,
) -> ExtractReport:
    """Citește paginile bifate. Logul primește doar numere și erori, nu titluri sau text."""
    lg = log.get("extract")
    started = time.monotonic()
    report = ExtractReport()
    lg.info("Extragere pornită (%s, %s)", source_label, "incremental" if incremental else "completă")
    t0 = time.monotonic()
    hierarchy = parse_hierarchy(source.get_hierarchy_xml())
    all_pages = hierarchy.pages()
    lg.info("Ierarhie citită în %.1f s: %d notebook-uri, %d secțiuni, %d pagini",
            time.monotonic() - t0, len(hierarchy.notebooks), sum(len(nb.sections) for nb in hierarchy.notebooks),
            len(all_pages))
    empty_sections = sum(1 for nb in hierarchy.notebooks for s in nb.sections if not s.pages)
    if empty_sections:
        lg.info("%d secțiuni fără nicio pagină în ierarhie (goale sau încă nesincronizate în OneNote)",
                empty_sections)

    previous: dict[str, Page] = {}
    if incremental and (out / PAGES_FILE).is_file():
        previous = {p.id: p for p in read_pages(out)}

    wanted = []
    for hp in all_pages:
        if selection.includes(hp.id, hp.notebook, hp.section_path):
            wanted.append(hp)
        else:
            report.skipped += 1
    lg.info("Bifate: %d pagini (sărite: %d; selecție: %d notebook-uri, %d secțiuni, %d pagini, excluse: %d)",
            len(wanted), report.skipped, len(selection.notebooks), len(selection.sections), len(selection.pages),
            len(selection.exclude_sections))
    if not wanted:
        lg.warning("Nicio pagină de citit: selecția nu se potrivește cu ierarhia sau secțiunile sunt goale")

    pages: list[Page] = []
    failures_in_a_row = 0
    last_log = time.monotonic()
    try:
        for n, hp in enumerate(wanted, start=1):
            if cancel and cancel():
                report.cancelled = True
                lg.warning("Extragere oprită de utilizator la pagina %d din %d", n, len(wanted))
                break
            if progress:
                progress(n, len(wanted), hp.title)
            old = previous.get(hp.id)
            if old and old.modified == hp.modified and all(image_path(out, i.sha256) for i in old.images):
                # pagina nu s-a schimbat; actualizăm doar locul (poate a fost mutată)
                old.notebook, old.section_path = hp.notebook, list(hp.section_path)
                pages.append(old)
                report.reused += 1
                continue
            t_page = time.monotonic()
            try:
                page, images = parse_page(source.get_page_xml(hp.id), hp.notebook, hp.section_path)
            except Exception as e:  # o pagină stricată nu oprește restul
                report.errors.append(f"{hp.notebook}/{'/'.join(hp.section_path)}/{hp.title}: {e}")
                lg.error("Pagina %d din %d nu s-a putut citi: %s", n, len(wanted), log.describe_error(e))
                failures_in_a_row += 1
                if report.fetched == 0 and failures_in_a_row >= abort_after:
                    report.aborted = log.describe_error(e)
                    raise _Abort from e
                continue
            failures_in_a_row = 0
            spent = time.monotonic() - t_page
            if spent > 20:
                lg.warning("Pagina %d din %d a durat %.0f s (%d imagini)", n, len(wanted), spent, len(images))
            save_images(out, images)
            pages.append(page)
            report.fetched += 1
            if checkpoint_every and report.fetched % checkpoint_every == 0:
                # salvare pe parcurs: dacă se oprește, următoarea rulare refolosește ce s-a citit
                seen = {p.id for p in pages}
                _write(out, pages + [p for p in previous.values() if p.id not in seen], selection, source_label)
            if time.monotonic() - last_log > 30:
                lg.info("Progres: %d din %d (citite %d, refolosite %d, erori %d)", n, len(wanted),
                        report.fetched, report.reused, len(report.errors))
                last_log = time.monotonic()
    except _Abort:
        lg.error("Extragere oprită: primele %d pagini au picat toate (%s). Nu s-a salvat nimic nou.",
                 abort_after, report.aborted)
        report.seconds = time.monotonic() - started
        return report

    report.removed = len(set(previous) - {p.id for p in pages})
    if report.cancelled:  # păstrăm și ce era citit înainte și n-am ajuns să verificăm
        seen = {p.id for p in pages}
        pages += [p for p in previous.values() if p.id not in seen]
        report.removed = 0
    _write(out, pages, selection, source_label)
    if not report.cancelled:
        remove_orphan_images(out, pages)
    report.seconds = time.monotonic() - started
    lg.info("Extragere gata în %.0f s: %d pagini (citite %d, refolosite %d, sărite %d, dispărute %d, erori %d)",
            report.seconds, report.total, report.fetched, report.reused, report.skipped, report.removed,
            len(report.errors))
    return report
