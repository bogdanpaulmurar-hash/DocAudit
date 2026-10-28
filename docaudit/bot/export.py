"""Exportul pentru bot: PDF pe pagină (cu trepte de rezervă), documente unite, lista de reîncărcat.

Trepte pe pagină (fiecare doar dacă cea de dinainte a eșuat), ca în vechiul script:
1. Publish PDF                         → fidelitate „full”
2. Publish Word, apoi Word → PDF       → „high” (merge la multe pagini cu fișiere atașate)
3. Publish pagină web (.mht) → PDF     → „medium”
4. textul extras de DocAudit → PDF     → „low”: pagina intră în lista „de verificat de mână”
Secțiunile cu parolă nu se pot exporta automat: pagina e trecută în listă.

Ce se scrie (totul local): `<extragere>/bot/pages/` (PDF-ul fiecărei pagini, refolosit cât
pagina nu se schimbă), `<extragere>/bot/last_run.json`, `export_pages.csv`, `reupload.txt`
și documentele finale în folderul ales (implicit `<extragere>/bot/out`). Din folderul final
se șterg doar fișierele scrise de un export anterior, nimic altceva.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .. import log
from ..extract.connect import OneNoteGone
from ..model import Page, image_path, read_manifest, read_pages
from . import guide
from .pdf import Item, merge, text_pdf
from ..extract.psbridge import BridgeUnavailable
from .publish import OfflinePublisher, Unsupported
from .select import BotPlan, bot_dir, build_plan

PAGES_DIR = "pages"
CACHE_FILE = "pages.json"
OUTPUTS_FILE = "outputs.json"
LAST_RUN = "last_run.json"
RECOVER = 5  # după ce OneNote a căzut: pauza înainte de procesul nou
MAX_CRASHES = 3  # atâtea pagini la rând cu OneNote căzut = oprim exportul
_lg = log.get("bot")


class ExportAborted(RuntimeError):
    fatal = True


@dataclass
class PageResult:
    id: str
    title: str
    doc: str
    method: str  # pdf | word | mht | text | cache | none
    fidelity: str  # full | high | medium | low | none
    note: str = ""  # password | crash | <cod eroare>
    file: str = ""


@dataclass
class ExportResult:
    out_dir: str = ""
    pages: list[PageResult] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)  # {"name", "doc", "size", "pages", "oversize"}
    reupload: list[str] = field(default_factory=list)
    removed_docs: list[str] = field(default_factory=list)
    skipped_pdf: list[list[str]] = field(default_factory=list)
    changes: dict = field(default_factory=dict)  # nou / modificat / mutat / scos față de exportul anterior
    instructions: str = ""
    instructions_changed: bool = False
    cancelled: bool = False
    seconds: float = 0.0
    finished_at: str = ""

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in self.pages:
            out[p.method] = out.get(p.method, 0) + 1
        return out

    def manual(self) -> list[PageResult]:
        return [p for p in self.pages if p.fidelity in ("low", "none") and p.method != "text-offline"]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["counts"] = self.counts()
        d["manual"] = [asdict(p) for p in self.manual()]
        return d


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _code(e: BaseException) -> str:
    """Doar codul erorii (0x8004…), pentru log și raport; fără text din pagini."""
    import re

    m = re.search(r"0x[0-9a-fA-F]{8}", str(e))
    return m.group(0).lower() if m else type(e).__name__


def page_html(folder: Path, page: Page) -> str:
    """Pagina refăcută din ce a extras DocAudit (text + imagini), pentru Word → PDF."""
    parts = [f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{html.escape(page.title)}</title></head>"
             f"<body style='font-family:Segoe UI,Arial'><h1>{html.escape(page.title)}</h1>"
             f"<p style='color:#888'>{html.escape(page.notebook + ' › ' + ' › '.join(page.section_path))}</p>"]
    for b in page.blocks or [type("B", (), {"type": "para", "text": line, "level": 0})()
                             for line in page.text.splitlines()]:
        text = html.escape(b.text)
        if b.type == "heading":
            parts.append(f"<h2>{text}</h2>")
        elif b.type == "list_item":
            parts.append(f"<p style='margin-left:{12 * max(b.level, 1)}px'>• {text}</p>")
        else:
            parts.append(f"<p>{text}</p>")
    for img in page.images:
        path = image_path(folder, img.sha256)
        if path:
            parts.append(f"<p><img src='{path.resolve().as_uri()}' style='max-width:100%'></p>")
    parts.append("</body></html>")
    return "".join(parts)


def _text_lines(page: Page) -> list[str]:
    lines = [" › ".join([page.notebook, *page.section_path]), ""]
    if page.blocks:
        lines += [("  " * b.level + "• " if b.type == "list_item" else "") + b.text for b in page.blocks]
    else:
        lines += page.text.splitlines()
    if page.images:
        lines += ["", f"[{len(page.images)} img]"]
    return lines


class _Exporter:
    def __init__(self, folder: Path, make_publisher: Callable[[], object], offline: bool, tmp: Path) -> None:
        self.folder, self.make, self.offline, self.tmp = folder, make_publisher, offline, tmp
        self.pub = None
        self.crashes = 0
        self.n = 0
        self.word_ok = False  # Word a mers măcar o dată
        self.word_fails = 0  # fără Word (nu e instalat): după câteva eșecuri nu-l mai încercăm

    def word_usable(self) -> bool:
        return self.word_ok or self.word_fails < 5

    def word(self, src: Path, dst: Path) -> bool:
        if not self.word_usable():
            return False
        try:
            self._call(lambda: (dst.unlink(missing_ok=True), self.publisher().word_to_pdf(src, dst)))
        except OneNoteGone:
            raise
        except Exception:
            self.word_fails += 1
            return False
        ok = dst.is_file() and dst.stat().st_size >= 300
        self.word_ok = self.word_ok or ok
        return ok

    def publisher(self):
        if self.pub is None:
            try:
                self.pub = self.make()
            except BridgeUnavailable as e:  # PowerShell nu poate porni OneNote: nimic nu se poate exporta
                raise ExportAborted(str(e)) from e
        return self.pub

    def close(self) -> None:
        if self.pub is not None:
            try:
                self.pub.close()
            except Exception:
                pass
            self.pub = None

    def _call(self, fn: Callable[[], None]) -> None:
        """Un apel spre OneNote / Word; dacă OneNote cade: proces nou și încă o încercare."""
        for attempt in (1, 2):
            try:
                fn()
                return
            except OneNoteGone:
                self.close()
                _lg.warning("OneNote nu mai răspunde la export (încercarea %d); reiau după %ss", attempt, RECOVER)
                time.sleep(RECOVER)
                if attempt == 2:
                    raise

    def _fresh(self, ext: str) -> Path:
        self.n += 1
        path = self.tmp / f"p{self.n:05d}.{ext}"
        path.unlink(missing_ok=True)
        return path

    def page(self, page: Page, dest: Path) -> tuple[str, str, str]:
        """Scrie PDF-ul paginii în `dest`; întoarce (metodă, fidelitate, notă)."""
        note = ""
        crashed = False
        if not self.offline:
            steps = (("pdf", "full", None), ("word", "high", "docx"), ("mht", "medium", "mht"))
            for fmt, fidelity, bridge in steps:
                out = self._fresh(bridge or "pdf")
                if bridge and not self.word_usable():
                    continue
                try:
                    self._call(lambda: (out.unlink(missing_ok=True), self.publisher().publish(page.id, out, fmt)))
                    if not out.is_file() or out.stat().st_size < 300:
                        note = note or "empty-file"
                        continue
                    if bridge:
                        pdf = self._fresh("pdf")
                        if not self.word(out, pdf):
                            note = note or "word"
                            continue
                        out = pdf
                    shutil.move(str(out), dest)
                    return fmt, fidelity, ""
                except OneNoteGone:
                    crashed = True
                    note = "crash"
                    break
                except ExportAborted:
                    raise
                except Unsupported:
                    break
                except Exception as e:
                    code = _code(e)
                    note = note or code
                    if code == "0x80042019":  # secțiune cu parolă: nimic nu merge automat
                        note = "password"
                        break
            if crashed:
                self.crashes += 1
                if self.crashes >= MAX_CRASHES:
                    raise ExportAborted(f"OneNote a căzut la {MAX_CRASHES} pagini la rând")
            else:
                self.crashes = 0
            if note == "password":
                return "none", "none", note
            # 4. din textul extras: întâi prin Word (păstrează diacriticele și imaginile), altfel PDF simplu
            src = self._fresh("html")
            src.write_text(page_html(self.folder, page), encoding="utf-8")
            pdf = self._fresh("pdf")
            try:
                if self.word(src, pdf):
                    shutil.move(str(pdf), dest)
                    return "text", "low", note
            except OneNoteGone:
                pass
        dest.write_bytes(text_pdf(page.title, _text_lines(page)))
        return ("text-offline", "low", "") if self.offline else ("text", "low", note)


def is_offline(folder: Path) -> bool:
    """Extragerea nu vine din OneNote desktop (eșantion, demo, fișiere importate): fără Publish."""
    m = read_manifest(folder)
    return m.source.kind != "onenote_com" or m.source.ref.startswith("demo")


def default_out_dir(folder: Path) -> Path:
    return bot_dir(folder) / "out"


def export(folder: Path, plan: BotPlan | None = None, *, out_dir: Path | None = None, max_mb: float = 95.0,
           level: str = "top", skip_stale: bool = True, skip_duplicates: bool = True, full: bool = False,
           make_publisher: Callable[[], object] | None = None, progress: Callable[[int, int], None] | None = None,
           cancel: Callable[[], bool] | None = None) -> ExportResult:
    t0 = time.monotonic()
    pages = {p.id: p for p in read_pages(folder)}
    plan = plan or build_plan(folder, level, skip_stale, skip_duplicates, list(pages.values()))
    offline = make_publisher is None and is_offline(folder)
    if make_publisher is None:
        if offline:
            make_publisher = OfflinePublisher
        else:  # pragma: no cover - Windows
            from .publish import PowerShellPublisher

            make_publisher = PowerShellPublisher
    out_dir = Path(out_dir) if out_dir else default_out_dir(folder)
    base = bot_dir(folder)
    cache_dir = base / PAGES_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = {} if full else _load(base / CACHE_FILE)
    result = ExportResult(out_dir=str(out_dir))
    wanted = [(doc["name"], pid) for doc in plan.documents for pid in doc["pages"] if pid in pages]
    total = len(wanted)
    tmp = Path(tempfile.mkdtemp(prefix="docaudit_"))
    ex = _Exporter(folder, make_publisher, offline, tmp)
    try:
        for i, (doc, pid) in enumerate(wanted, 1):
            if cancel and cancel():
                result.cancelled = True
                break
            page = pages[pid]
            file = hashlib.sha1(pid.encode("utf-8")).hexdigest()[:20] + ".pdf"
            dest = cache_dir / file
            old = cache.get(pid)
            if (old and old.get("modified") == page.modified and old.get("fidelity") not in ("low", "none")
                    and dest.is_file()):
                result.pages.append(PageResult(pid, page.title, doc, "cache", old["fidelity"], file=file))
            else:
                dest.unlink(missing_ok=True)
                method, fidelity, note = ex.page(page, dest)
                if dest.is_file():
                    cache[pid] = {"modified": page.modified, "file": file, "method": method, "fidelity": fidelity,
                                  "sha256": _sha256(dest)}
                else:
                    cache.pop(pid, None)
                result.pages.append(PageResult(pid, page.title, doc, method, fidelity, note, file if dest.is_file()
                                               else ""))
            if i % 20 == 0:
                _save(base / CACHE_FILE, cache)
            if progress:
                progress(i, total)
        _save(base / CACHE_FILE, cache)
        if not result.cancelled:
            _build_documents(folder, plan, result, cache, out_dir, max_mb, pages, ex)
    finally:
        ex.close()
        shutil.rmtree(tmp, ignore_errors=True)
        _save(base / CACHE_FILE, cache)
    result.seconds = round(time.monotonic() - t0, 1)
    result.finished_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    counts = result.counts()
    _lg.info("Export pentru bot: %d pagini (%s), %d fișiere, %d de reîncărcat, %d de verificat de mână, %.1f s%s",
             len(result.pages), ", ".join(f"{k} {v}" for k, v in sorted(counts.items())), len(result.files),
             len(result.reupload), len(result.manual()), result.seconds, " (oprit)" if result.cancelled else "")
    _write_reports(base, result)
    return result


def _build_documents(folder: Path, plan: BotPlan, result: ExportResult, cache: dict, out_dir: Path,
                     max_mb: float, pages: dict[str, Page], ex: "_Exporter | None" = None) -> None:
    base = bot_dir(folder)
    previous = _load(base / OUTPUTS_FILE)
    old_fp: dict[str, str] = previous.get("fingerprints", {}) if previous.get("out_dir") == str(out_dir) else {}
    by_page = {p.id: p for p in result.pages}
    written: list[str] = []
    fingerprints: dict[str, str] = {}
    max_bytes = int(max_mb * 1024 * 1024)
    for doc in plan.documents:
        items, fp = [], hashlib.sha256()
        for pid in doc["pages"]:
            r, c = by_page.get(pid), cache.get(pid)
            if not r or not c:
                continue
            items.append(Item(base / PAGES_DIR / c["file"], r.title))
            # pagina schimbată în OneNote (sau exportată altfel) = documentul trebuie reîncărcat
            fp.update(f"{pid}\t{c['modified']}\t{c['method']}\t{r.title}\n".encode("utf-8"))
        if not items:
            continue
        # părțile vechi ale acestui document se șterg înainte (numărul de părți se poate schimba)
        for name in previous.get("files", []) if previous.get("out_dir") == str(out_dir) else []:
            if name == f"{doc['name']}.pdf" or name.startswith(f"{doc['name']}_Part"):
                (out_dir / name).unlink(missing_ok=True)
        merged = merge(items, out_dir, doc["name"], max_bytes)
        fingerprints[doc["name"]] = fp.hexdigest()
        names = [p.path.name for p in merged.parts]
        written += names
        for p in merged.parts:
            result.files.append({"name": p.path.name, "doc": doc["name"], "size": p.size, "pages": p.pages,
                                 "oversize": p.oversize})
        old_files = set(previous.get("files", [])) if old_fp else set()
        if old_fp.get(doc["name"]) != fingerprints[doc["name"]] or not set(names) <= old_files:
            result.reupload += names
        result.skipped_pdf += [list(s) for s in merged.skipped]
    # cuprinsul (cu ce s-a schimbat) și instrucțiunile botului
    same_dir = previous.get("out_dir") == str(out_dir)
    exported = {pid for pid, r in by_page.items() if r.file and pid in cache}
    current = guide.page_map(plan, pages, exported)
    ch = guide.changes(previous.get("pages"), current)
    result.changes = ch.to_dict()
    when = time.strftime("%Y-%m-%d %H:%M")
    # în cuprins rămân ultimele schimbări reale (cu data lor), ca un export fără noutăți să nu-l schimbe
    shown, shown_when = ch, when
    if not ch.first and not ch.count() and previous.get("last_changes"):
        shown = guide.Changes(**{k: [tuple(x) for x in v] if isinstance(v, list) else v
                                 for k, v in previous["last_changes"].items()})
        shown_when = previous.get("last_changes_at", "")
    files_by_doc: dict[str, list[str]] = {}
    for f in result.files:
        files_by_doc.setdefault(f["doc"], []).append(f["name"])
    lines = guide.index_lines(plan, pages, files_by_doc, shown, exported, shown_when)
    index_hash = guide.text_hash(lines)
    out_dir.mkdir(parents=True, exist_ok=True)
    index_changed = index_hash != (previous.get("index_hash") if same_dir else None)
    if index_changed or not (out_dir / guide.INDEX_FILE).is_file():
        _index_pdf(out_dir / guide.INDEX_FILE, [f"Export: {when}", *lines], ex)
    written.append(guide.INDEX_FILE)
    if index_changed:
        result.reupload.insert(0, guide.INDEX_FILE)
    result.instructions = guide.instructions(plan, pages, files_by_doc, exported, when)
    instructions_hash = guide.text_hash(guide.instructions(plan, pages, files_by_doc, exported, ""))
    result.instructions_changed = instructions_hash != previous.get("instructions_hash")
    (out_dir / guide.INSTRUCTIONS_FILE).write_text(result.instructions, encoding="utf-8")
    written.append(guide.INSTRUCTIONS_FILE)
    _append_history(bot_dir(folder), when, ch)

    # documentele care nu mai există (ex. toate paginile scoase): fișierele lor vechi pleacă
    if same_dir:
        for name in previous.get("files", []):
            if name not in written:
                (out_dir / name).unlink(missing_ok=True)
        result.removed_docs = sorted(set(old_fp) - set(fingerprints))
    _save(base / OUTPUTS_FILE, {"out_dir": str(out_dir), "files": written, "fingerprints": fingerprints,
                                "pages": current, "index_hash": index_hash, "instructions_hash": instructions_hash,
                                "last_changes": shown.to_dict(), "last_changes_at": shown_when})


def _index_pdf(dest: Path, lines: list[str], ex: "_Exporter | None") -> None:
    """Cuprinsul prin Word, ca să păstreze diacriticele; fără Word, PDF-ul simplu (fără ă, ș, ț)."""
    title = "Cuprins / Inhaltsverzeichnis"
    if ex is not None and not ex.offline:
        src = ex._fresh("html")
        body = "".join(f"<p style='margin:0;white-space:pre-wrap'>{html.escape(line) or '&nbsp;'}</p>" for line in lines)
        src.write_text(f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title></head>"
                       f"<body style='font-family:Segoe UI,Arial;font-size:10pt'><h1>{title}</h1>{body}</body></html>",
                       encoding="utf-8")
        pdf = ex._fresh("pdf")
        try:
            if ex.word(src, pdf):
                shutil.move(str(pdf), dest)
                return
        except OneNoteGone:
            pass
    dest.write_bytes(text_pdf(title, lines))


def _append_history(base: Path, when: str, ch: guide.Changes) -> None:
    """Istoricul exporturilor (local, pentru tine): ce a intrat nou, ce s-a schimbat, ce s-a mutat."""
    lines = [f"## {when}"]
    if ch.first:
        lines.append("- primul export")
    else:
        lines.append(f"- nou {len(ch.new)}, modificat {len(ch.modified)}, mutat {len(ch.moved)}, scos {len(ch.removed)}")
        lines += [f"  - nou: {t} [{d}]" for t, d in ch.new]
        lines += [f"  - modificat: {t} [{d}]" for t, d in ch.modified]
        lines += [f"  - mutat: {t}: {a} -> {b}" for t, a, b in ch.moved]
        lines += [f"  - scos: {t} [{d}]" for t, d in ch.removed]
    with (base / "istoric_modificari.md").open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n")


def foreign_files(folder: Path, out_dir: Path) -> list[str]:
    """Fișierele din folderul documentelor pe care nu le-a scris DocAudit (de ex. de la scriptul vechi)."""
    if not out_dir.is_dir():
        return []
    previous = _load(bot_dir(folder) / OUTPUTS_FILE)
    ours = set(previous.get("files", [])) if previous.get("out_dir") == str(out_dir) else set()
    ours |= {guide.INDEX_FILE, guide.INSTRUCTIONS_FILE}
    return sorted((p.name for p in out_dir.iterdir() if p.is_file() and p.name not in ours
                   and not p.name.startswith(("~$", "."))), key=str.casefold)


def move_foreign(folder: Path, out_dir: Path, names: list[str]) -> Path | None:
    """Mută fișierele străine într-un subfolder `_vechi_<dată>` (nu le șterge)."""
    allowed = set(foreign_files(folder, out_dir))
    picked = [n for n in names if n in allowed]
    if not picked:
        return None
    target = out_dir / time.strftime("_vechi_%Y%m%d-%H%M%S")
    target.mkdir(parents=True, exist_ok=True)
    for name in picked:
        shutil.move(str(out_dir / name), str(target / name))
    _lg.info("Export pentru bot: %d fișiere vechi mutate în subfolder", len(picked))
    return target


def _write_reports(base: Path, result: ExportResult) -> None:
    _save(base / LAST_RUN, result.to_dict())
    with (base / "export_pages.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page_id", "title", "document", "method", "fidelity", "note", "file"])
        for p in result.pages:
            w.writerow([p.id, p.title, p.doc, p.method, p.fidelity, p.note, p.file])
    if not result.cancelled:
        (base / "reupload.txt").write_text("\n".join(result.reupload) + ("\n" if result.reupload else ""),
                                           encoding="utf-8")


def last_run(folder: Path) -> dict | None:
    data = _load(bot_dir(folder) / LAST_RUN)
    return data or None
