"""„Aplică”: previzualizare, copie de siguranță, scriere în OneNote, restaurare.

Reguli (din CLAUDE.md):
- nimic nu se scrie fără decizia utilizatorului și fără ca modul doar citire să fie oprit din setări;
- întâi previzualizarea (plan); se aplică doar deciziile confirmate din previzualizare;
- înainte de orice scriere, XML-ul complet al paginii se salvează în copii de siguranță;
- arhivare = copie în secțiunea „Arhivă” cu nota „Mutat din …” + originalul în Coșul OneNote;
- mutare în altă secțiune (aleasă de utilizator) = la fel, doar că ținta e secțiunea aleasă;
- o pagină modificată în OneNote după extragere nu se atinge (se cere o extragere nouă).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..decisions import Journal, split_target
from ..extract.onenote_xml import parse_hierarchy
from ..i18n import t
from ..model import read_pages
from ..paths import backups_dir
from ..settings import Settings
from .writer import WritableOneNote
from .xmlops import copy_page_xml, has_prefix, prefixed_title, title_html_of, title_update_xml


class WriteDisabled(RuntimeError):
    """Modul doar citire e pornit: scrierea în OneNote nu e permisă."""


@dataclass
class PlanItem:
    decision_id: int
    action: str
    page_id: str
    title: str
    notebook: str
    section: str
    target: str  # secțiunea de arhivă, secțiunea aleasă la mutare sau noul titlu
    status: str  # ready | skip
    reason: str = ""  # cheie: missing, changed, already_archived, already_marked, create_section,
    #                   already_there, no_target

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ApplyResult:
    done: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _today() -> str:
    return datetime.now().strftime("%d.%m.%Y")


def _locate(writer: WritableOneNote) -> dict[str, dict]:
    """page_id -> locul ei acum în OneNote (notebook, secțiune, data modificării)."""
    out = {}
    for nb in parse_hierarchy(writer.get_hierarchy_xml()).notebooks:
        for sec in nb.sections:
            for p in sec.pages:
                out[p.id] = {"notebook": nb.name, "notebook_id": nb.id, "section": "/".join(sec.path),
                             "section_id": sec.id, "modified": p.modified, "title": p.title}
    return out


def _archive_section(writer: WritableOneNote, notebook_id: str, name: str) -> str | None:
    for nb in parse_hierarchy(writer.get_hierarchy_xml()).notebooks:
        if nb.id == notebook_id:
            for sec in nb.sections:
                if sec.path == [name]:
                    return sec.id
    return None


def _section_by_path(writer: WritableOneNote, notebook: str, path: str) -> str | None:
    """Id-ul secțiunii „path” din notebook-ul „notebook” (după nume), dacă există acum în OneNote."""
    for nb in parse_hierarchy(writer.get_hierarchy_xml()).notebooks:
        if nb.name == notebook:
            for sec in nb.sections:
                if "/".join(sec.path) == path:
                    return sec.id
    return None


def plan(folder: Path, writer: WritableOneNote, settings: Settings) -> list[PlanItem]:
    """Ce s-ar întâmpla la „Aplică”. Doar citește din OneNote."""
    journal = Journal(folder)
    pages = {p.id: p for p in read_pages(folder)}
    where = _locate(writer)
    items = []
    for d in sorted(journal.pending(), key=lambda d: d.id):
        page = pages.get(d.page_id)
        loc = where.get(d.page_id)
        title = page.title if page else d.page_id
        if loc is None:
            items.append(PlanItem(d.id, d.action, d.page_id, title, "", "", "", "skip", "missing"))
            continue
        base = dict(decision_id=d.id, action=d.action, page_id=d.page_id, title=loc["title"] or title,
                    notebook=loc["notebook"], section=loc["section"])
        if page is not None and page.modified != loc["modified"]:
            items.append(PlanItem(**base, target="", status="skip", reason="changed"))
        elif d.action == "move":
            nb_name, sec_path = split_target(d.target)
            shown = f"{nb_name} › {sec_path}" if nb_name != loc["notebook"] else sec_path
            if nb_name == loc["notebook"] and sec_path == loc["section"]:
                items.append(PlanItem(**base, target=shown, status="skip", reason="already_there"))
            elif not _section_by_path(writer, nb_name, sec_path):
                items.append(PlanItem(**base, target=shown, status="skip", reason="no_target"))
            else:
                items.append(PlanItem(**base, target=shown, status="ready"))
        elif d.action == "archive":
            if loc["section"] == settings.archive_section:
                items.append(PlanItem(**base, target=settings.archive_section, status="skip",
                                      reason="already_archived"))
            else:
                exists = _archive_section(writer, loc["notebook_id"], settings.archive_section)
                items.append(PlanItem(**base, target=settings.archive_section, status="ready",
                                      reason="" if exists else "create_section"))
        else:
            if loc["title"].startswith(settings.stale_prefix.strip()):
                items.append(PlanItem(**base, target=loc["title"], status="skip", reason="already_marked"))
            else:
                items.append(PlanItem(**base, target=settings.stale_prefix + loc["title"], status="ready"))
    return items


def _backup(xml: str, page_id: str, meta: dict) -> Path:
    folder = backups_dir() / datetime.now().strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    stem = datetime.now().strftime("%H%M%S-") + (re.sub(r"[^0-9A-Za-z]+", "", page_id)[:40] or "pagina")
    path = folder / f"{stem}.xml"
    n = 1
    while path.exists():
        path = folder / f"{stem}-{n}.xml"
        n += 1
    path.write_text(xml, encoding="utf-8", newline="\n")
    path.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8", newline="\n")
    return path


def apply(folder: Path, writer: WritableOneNote, settings: Settings, decision_ids: list[int],
          lang: str | None = None) -> ApplyResult:
    """Aplică doar deciziile confirmate (din previzualizare). Fiecare pagină: copie de siguranță, apoi scriere."""
    if not settings.write_enabled:
        raise WriteDisabled(t("apply.disabled", lang))
    journal = Journal(folder)
    decisions = {d.id: d for d in journal.pending()}
    result = ApplyResult()
    wanted = set(decision_ids)
    for item in plan(folder, writer, settings):
        if item.decision_id not in wanted:
            continue
        if item.status != "ready":
            result.skipped.append(item.to_dict())
            continue
        loc = _locate(writer)[item.page_id]
        try:
            xml = writer.get_page_xml(item.page_id)
            backup = _backup(xml, item.page_id, {**item.to_dict(), "section_id": loc["section_id"],
                                                 "notebook_id": loc["notebook_id"]})
            d = decisions[item.decision_id]
            if item.action in ("archive", "move"):
                if item.action == "move":
                    section_id = _section_by_path(writer, *split_target(d.target))
                    if not section_id:
                        result.skipped.append({**item.to_dict(), "reason": "no_target"})
                        continue
                else:
                    section_id = _archive_section(writer, loc["notebook_id"], settings.archive_section) \
                        or writer.create_section(loc["notebook_id"], settings.archive_section)
                new_id = writer.create_page(section_id)
                note = t("apply.note", lang, section=item.section, date=_today(),
                         reason=d.note or t("apply.reason.default", lang))
                writer.update_page(copy_page_xml(xml, new_id, note))
                writer.delete_page(item.page_id)  # în Coșul OneNote, recuperabilă
                journal.record_applied(d.id, item.action, item.page_id, item.title, notebook_id=loc["notebook_id"],
                                       section_id=loc["section_id"], section=item.section, new_page_id=new_id,
                                       backup=str(backup))
            else:
                old = title_html_of(xml)
                if has_prefix(old, settings.stale_prefix):
                    result.skipped.append({**item.to_dict(), "reason": "already_marked"})
                    continue
                partial, _ = title_update_xml(xml, prefixed_title(old, settings.stale_prefix))
                writer.update_page(partial)
                journal.record_applied(d.id, "mark_stale", item.page_id, item.title, notebook_id=loc["notebook_id"],
                                       section_id=loc["section_id"], section=item.section, old_title_html=old,
                                       backup=str(backup))
            result.done.append(item.to_dict())
        except Exception as e:  # o pagină care nu merge nu le oprește pe celelalte
            result.errors.append({**item.to_dict(), "error": str(e)})
    return result


def restore(folder: Path, writer: WritableOneNote, settings: Settings, applied_id: int,
            lang: str | None = None) -> dict:
    """Întoarce o pagină arhivată / mutată în secțiunea ei sau scoate prefixul „[ÎNVECHIT]”."""
    if not settings.write_enabled:
        raise WriteDisabled(t("apply.disabled", lang))
    journal = Journal(folder)
    row = journal.get_applied(applied_id)
    if row is None or row["restored_at"]:
        raise ValueError(t("apply.restore.none", lang))
    where = _locate(writer)
    if row["action"] in ("archive", "move"):
        if row["new_page_id"] not in where:
            raise ValueError(t("apply.restore.missing", lang))
        if not any(loc["section_id"] == row["section_id"] for loc in where.values()) and \
                not _section_exists(writer, row["section_id"]):
            raise ValueError(t("apply.restore.nosection", lang, section=row["section"]))
        xml = Path(row["backup"]).read_text("utf-8")
        new_id = writer.create_page(row["section_id"])
        writer.update_page(copy_page_xml(xml, new_id))
        writer.delete_page(row["new_page_id"])
        out = {"page_id": new_id, "section": row["section"]}
    else:
        if row["page_id"] not in where:
            raise ValueError(t("apply.restore.missing", lang))
        partial, _ = title_update_xml(writer.get_page_xml(row["page_id"]), row["old_title_html"])
        writer.update_page(partial)
        out = {"page_id": row["page_id"], "section": row["section"]}
    journal.mark_restored(applied_id, row["decision_id"])
    return out


def _section_exists(writer: WritableOneNote, section_id: str) -> bool:
    return any(sec.id == section_id for nb in parse_hierarchy(writer.get_hierarchy_xml()).notebooks
               for sec in nb.sections)


DEMO_ONENOTE = "demo_onenote.json"


def writer_for(folder: Path, lang: str | None = None) -> WritableOneNote:
    """OneNote-ul în care se aplică deciziile pentru această extragere."""
    from ..model import read_manifest
    from ..paths import data_dir
    from .writer import ComOneNote, FakeOneNote

    source = read_manifest(folder).source
    if source.kind == "onenote_com" and source.ref.startswith("demo"):
        path = data_dir() / DEMO_ONENOTE
        return FakeOneNote(path) if path.is_file() else FakeOneNote.from_sample(path)
    if source.kind != "onenote_com":
        raise WriteDisabled(t("apply.notonenote", lang))
    from ..extract.psbridge import BridgeUnavailable  # pragma: no cover - Windows
    from .pswriter import PowerShellWriter  # pragma: no cover - Windows

    try:  # pragma: no cover - Windows
        return PowerShellWriter()  # aceeași cale ca la citire; prin pywin32 OneNote cădea pe unele laptopuri
    except BridgeUnavailable:  # pragma: no cover - Windows
        return ComOneNote()
