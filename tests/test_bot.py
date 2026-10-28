"""„Export pentru bot”: alegerea paginilor, PDF pe pagină cu trepte de rezervă, unire sub limită, reîncărcare."""

import dataclasses
import http.client
import json
import shutil
import threading

import pytest
from pypdf import PdfReader

from docaudit.bot import export as bot_export
from docaudit.bot.export import ExportAborted, export, foreign_files, last_run, move_foreign
from docaudit.bot.guide import INDEX_FILE, INSTRUCTIONS_FILE
from docaudit.bot.pdf import Item, merge, text_pdf
from docaudit.bot.publish import FORMATS, SCRIPT
from docaudit.bot.select import build_plan, content_key, safe_name, set_override
from docaudit.compare.run import run_compare
from docaudit.decisions import Journal, make_target
from docaudit.extract.connect import OneNoteGone
from docaudit.group.run import run_grouping
from docaudit.lang import is_untitled
from docaudit.model import read_manifest, read_pages, write_dataset
from docaudit.settings import Settings, update_settings


@pytest.fixture
def ds(tmp_path, fixture_dir, monkeypatch):
    """Eșantionul analizat + o copie identică a unei pagini, o pagină goală și una „Untitled page”."""
    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path / "data"))
    folder = tmp_path / "data" / "mostra"
    shutil.copytree(fixture_dir, folder)
    pages = read_pages(folder)
    first = pages[0]
    copy = dataclasses.replace(first, id="copie-1", section_path=list(pages[-1].section_path),
                               modified="2020-01-01T00:00:00Z")
    empty = dataclasses.replace(first, id="goala-1", title="Pagină nouă", text="", blocks=[], images=[],
                                attachments=[])
    untitled = dataclasses.replace(first, id="fara-titlu-1", title="Untitled page 3", text="Ceva text unic aici.",
                                   blocks=[], images=[])
    pages += [copy, empty, untitled]
    write_dataset(folder, read_manifest(folder), pages)
    run_grouping(folder)
    run_compare(folder)
    return folder


def _reasons(plan):
    return {p.id: p.reason for p in plan.pages if not p.included}


# ---------- alegerea paginilor ----------

def test_untitled_titles_in_three_languages():
    for title in ("", "Untitled page", "Untitled_page 2", "Fără titlu", "Pagină fără titlu", "Unbenannte Seite 4",
                  "Ohne Titel", "  "):
        assert is_untitled(title), title
    for title in ("Resetarea parolei", "Untitled procedure for VPN", "Seite einrichten"):
        assert not is_untitled(title), title


def test_plan_leaves_out_duplicates_empty_stale_and_archived(ds):
    pages = {p.id: p for p in read_pages(ds)}
    first = next(iter(pages))
    plan = build_plan(ds)
    reasons = _reasons(plan)
    assert reasons["copie-1"] == "duplicate"  # copia mai veche pleacă, originalul rămâne
    assert first not in reasons
    assert next(p for p in plan.pages if p.id == "copie-1").duplicate_of == first
    assert reasons["goala-1"] == "empty"
    untitled = next(p for p in plan.pages if p.id == "fara-titlu-1")
    assert untitled.included and untitled.untitled  # are conținut: intră, dar e semnalată
    expected = json.loads((ds / "expected.json").read_text("utf-8"))
    assert {pid for pid, r in reasons.items() if r == "stale"} == set(expected["stale"])
    assert plan.counts()["included"] == len(pages) - len(reasons)
    # fiecare pagină inclusă e într-un singur document
    in_docs = [pid for d in plan.documents for pid in d["pages"]]
    assert len(in_docs) == len(set(in_docs)) == plan.counts()["included"]

    # decizii: arhivată iese; „păstrează” readuce o pagină învechită; referința câștigă la duplicate
    stale_page = expected["stale"][0]
    j = Journal(ds)
    j.add(first, "archive")
    j.add(stale_page, "keep")
    j.add("copie-1", "reference")
    reasons = _reasons(build_plan(ds))
    assert reasons[first] == "archived" and stale_page not in reasons and "copie-1" not in reasons

    # fără filtre: doar goala și arhivata rămân deoparte
    assert set(_reasons(build_plan(ds, skip_stale=False, skip_duplicates=False))) == {"goala-1", first}


def test_overrides_and_levels(ds):
    plan = build_plan(ds)
    stale = next(pid for pid, r in _reasons(plan).items() if r == "stale")
    keep = next(p.id for p in plan.pages if p.included)
    set_override(ds, stale, "include")
    set_override(ds, keep, "exclude")
    plan = build_plan(ds)
    by_id = {p.id: p for p in plan.pages}
    assert by_id[stale].included and by_id[stale].override == "include"
    assert not by_id[keep].included and by_id[keep].reason == "excluded"
    set_override(ds, keep, None)
    assert next(p for p in build_plan(ds).pages if p.id == keep).included
    with pytest.raises(ValueError):
        set_override(ds, keep, "sterge")

    notebooks = {p.notebook for p in read_pages(ds)}
    assert len(build_plan(ds, level="notebook").documents) == len(notebooks)
    assert len(build_plan(ds, level="section").documents) >= len(build_plan(ds, level="top").documents)
    with pytest.raises(ValueError):
        build_plan(ds, level="pagina")


def test_move_decision_puts_page_in_target_document(ds):
    pages = read_pages(ds)
    page = next(p for p in pages if p.notebook != pages[-1].notebook)
    target = pages[-1]
    Journal(ds).add(page.id, "move", target=make_target(target.notebook, "/".join(target.section_path)))
    plan = build_plan(ds, level="section")
    moved = next(p for p in plan.pages if p.id == page.id)
    other = next(p for p in plan.pages if p.id == target.id)
    assert moved.doc == other.doc


def test_safe_name_and_content_key():
    assert safe_name('a/b:c*?"<>| ') == "a_b_c_"
    assert safe_name("...") == "Document"
    assert len(safe_name("x" * 300)) == 80
    assert safe_name("Proceduri IT - Rețea") == "Proceduri IT - Rețea"


# ---------- PDF ----------

def test_text_pdf_is_valid_and_keeps_romanian_letters_readable(tmp_path):
    path = tmp_path / "p.pdf"
    path.write_bytes(text_pdf("Resetare parolă (veche)", ["Pasul 1: apasă «OK»", "Schritt 2: Größe ändern"] * 50))
    reader = PdfReader(str(path))
    assert len(reader.pages) == 2
    text = reader.pages[0].extract_text()
    assert "Resetare parola (veche)" in text and "Größe" in text


def test_merge_splits_under_limit_with_bookmarks(tmp_path):
    items = []
    for i in range(6):
        p = tmp_path / f"{i}.pdf"
        p.write_bytes(text_pdf(f"Pagina {i}", [f"rand {j} " * 10 for j in range(40 * (i + 1))]))
        items.append(Item(p, f"Pagina {i}"))
    out = tmp_path / "out"
    one = merge(items, out, "Tot", 50 * 1024 * 1024)
    assert [p.path.name for p in one.parts] == ["Tot.pdf"]
    titles = [o.title for o in PdfReader(str(out / "Tot.pdf")).outline]
    assert titles == [f"Pagina {i}" for i in range(6)]

    limit = 9000
    split = merge(items, out, "Mic", limit)
    assert len(split.parts) > 1
    assert [p.path.name for p in split.parts] == [f"Mic_Part{i}.pdf" for i in range(1, len(split.parts) + 1)]
    seen = []
    for part in split.parts:
        assert part.size <= limit or (part.items == 1 and part.oversize)
        seen += [o.title for o in PdfReader(str(part.path)).outline]
    assert seen == [f"Pagina {i}" for i in range(6)]  # nicio pagină pierdută sau ruptă

    bad = tmp_path / "rau.pdf"
    bad.write_bytes(b"nu e pdf")
    r = merge([items[0], Item(bad, "Stricat")], out, "Cu greseli", 50 * 1024 * 1024)
    assert r.skipped and r.skipped[0][0] == "Stricat" and r.parts[0].pages == 1


# ---------- exportul, cu un OneNote fals ----------

class FakePublisher:
    """Publish fals: ce cere testul pentru fiecare pagină (după id) și format."""

    def __init__(self, rules, word=True, crash_once=(), always_crash=()):
        self.rules, self.word, self.crash_once, self.always_crash = rules, word, set(crash_once), set(always_crash)
        self.calls = []
        self.closed = 0

    def publish(self, page_id, path, fmt):
        self.calls.append((page_id, fmt))
        assert fmt in FORMATS and not path.exists()
        if page_id in self.always_crash or (page_id, fmt) in self.crash_once:
            self.crash_once.discard((page_id, fmt))
            raise OneNoteGone("Publish", -2147023174, False)
        rule = self.rules.get(page_id, {}).get(fmt, "ok")
        if rule != "ok":
            raise RuntimeError(f"Publish (PowerShell): {rule} eroare")
        path.write_bytes(text_pdf(f"{page_id} {fmt}", ["x" * 80] * 10) if fmt == "pdf" else b"doc" * 200)

    def word_to_pdf(self, src, dst):
        self.calls.append((src.suffix, "word"))
        if not self.word:
            raise RuntimeError("Word (PowerShell): 0x80040154 Class not registered")
        if src.suffix == ".html":  # „Word” fals: textul din HTML, ca să se poată verifica
            import re

            lines = [re.sub(r"<[^>]+>", "", x) for x in src.read_text("utf-8").split("</p>")]
            dst.write_bytes(text_pdf("word", lines))
        else:
            dst.write_bytes(text_pdf(f"word {src.suffix}", ["y" * 80] * 10))

    def close(self):
        self.closed += 1


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(bot_export, "RECOVER", 0)


def test_export_fallback_steps(ds, tmp_path, fast):
    plan = build_plan(ds)
    ids = [pid for d in plan.documents for pid in d["pages"]]
    a, b, c, d, e = ids[:5]
    fake = FakePublisher({
        b: {"pdf": "0x80042006"},  # pagină cu fișier atașat: merge prin Word
        c: {"pdf": "0x80042006", "word": "0x80042006"},  # merge prin pagina web
        d: {"pdf": "0x80042006", "word": "0x80042006", "mht": "0x80042006"},  # doar textul
        e: {"pdf": "0x80042019"},  # secțiune cu parolă
    })
    out = tmp_path / "bot"
    r = export(ds, plan, out_dir=out, make_publisher=lambda: fake)
    by = {p.id: p for p in r.pages}
    assert (by[a].method, by[a].fidelity) == ("pdf", "full")
    assert (by[b].method, by[b].fidelity) == ("word", "high")
    assert (by[c].method, by[c].fidelity) == ("mht", "medium")
    assert (by[d].method, by[d].fidelity, by[d].note) == ("text", "low", "0x80042006")
    assert (by[e].method, by[e].note) == ("none", "password")
    assert {m.id for m in r.manual()} == {d, e}
    assert ("pdf" in [f for pid, f in fake.calls if pid == e]) and [f for pid, f in fake.calls if pid == e] == ["pdf"]
    # documentele: toate paginile exportate, cu semn de carte; cea cu parolă lipsește
    titles = []
    for f in r.files:
        titles += [o.title for o in PdfReader(str(out / f["name"])).outline]
    exported = [p for p in r.pages if p.file]
    assert len(titles) == len(exported) == len(r.pages) - 1
    assert sorted(r.reupload) == sorted([INDEX_FILE] + [f["name"] for f in r.files])  # primul export: totul e nou
    assert (ds / "bot" / "export_pages.csv").is_file()
    assert last_run(ds)["counts"]["pdf"] == len(r.pages) - 4


def test_export_reuses_pages_and_lists_only_changed_documents(ds, tmp_path, fast):
    out = tmp_path / "bot"
    out.mkdir()
    (out / "manual.pdf").write_bytes(b"al utilizatorului")  # nu e al DocAudit: nu se atinge
    plan = build_plan(ds)
    r1 = export(ds, plan, out_dir=out, make_publisher=lambda: FakePublisher({}))
    assert r1.reupload
    fake = FakePublisher({})
    r2 = export(ds, plan, out_dir=out, make_publisher=lambda: fake)
    assert r2.reupload == [] and fake.calls == []  # nimic schimbat: nimic de cerut OneNote, nimic de reîncărcat
    assert {p.method for p in r2.pages} == {"cache"}

    # o pagină schimbată în OneNote → doar documentul ei se reîncarcă
    pages = read_pages(ds)
    changed = plan.documents[0]["pages"][0]
    pages = [dataclasses.replace(p, modified="2030-01-01T00:00:00Z") if p.id == changed else p for p in pages]
    write_dataset(ds, read_manifest(ds), pages)
    r3 = export(ds, build_plan(ds), out_dir=out, make_publisher=lambda: FakePublisher({}))
    assert r3.reupload == [INDEX_FILE, f"{plan.documents[0]['name']}.pdf"]  # cuprinsul spune ce s-a schimbat
    assert [t for t, _ in r3.changes["modified"]] == [next(p.title for p in pages if p.id == changed)]
    assert not r3.instructions_changed

    # un document dispărut: fișierul lui vechi pleacă, al utilizatorului rămâne
    for pid in plan.documents[1]["pages"]:
        set_override(ds, pid, "exclude")
    r4 = export(ds, build_plan(ds), out_dir=out, make_publisher=lambda: FakePublisher({}))
    assert r4.removed_docs == [plan.documents[1]["name"]]
    assert not (out / f"{plan.documents[1]['name']}.pdf").exists()
    assert (out / "manual.pdf").read_bytes() == b"al utilizatorului"


def test_export_recovers_from_one_crash_and_stops_after_many(ds, tmp_path, fast):
    plan = build_plan(ds)
    ids = [pid for d in plan.documents for pid in d["pages"]]
    fake = FakePublisher({}, crash_once={(ids[0], "pdf")})
    r = export(ds, plan, out_dir=tmp_path / "a", make_publisher=lambda: fake)
    assert next(p for p in r.pages if p.id == ids[0]).method == "pdf"  # proces nou, a doua încercare a mers
    assert fake.closed >= 1

    fake = FakePublisher({}, always_crash=set(ids[:5]))
    with pytest.raises(ExportAborted):
        export(ds, plan, out_dir=tmp_path / "b", full=True, make_publisher=lambda: fake)


def test_export_without_word_and_cancel(ds, tmp_path, fast):
    plan = build_plan(ds)
    ids = [pid for d in plan.documents for pid in d["pages"]]
    fake = FakePublisher({pid: {"pdf": "0x80042006"} for pid in ids[:8]}, word=False)
    r = export(ds, plan, out_dir=tmp_path / "a", make_publisher=lambda: fake)
    assert {p.method for p in r.pages if p.id in ids[:8]} == {"text"}  # PDF simplu din text
    assert sum(1 for x in fake.calls if x[1] == "word" and x[0].startswith(".")) <= 5  # fără Word: nu-l mai încearcă la nesfârșit

    seen = []
    r = export(ds, plan, out_dir=tmp_path / "b", full=True, make_publisher=lambda: FakePublisher({}),
               progress=lambda n, total: seen.append(n), cancel=lambda: len(seen) >= 3)
    assert r.cancelled and len(r.pages) == 3 and r.files == []


def test_offline_dataset_exports_text(ds, tmp_path):
    r = export(ds, out_dir=tmp_path / "o")  # eșantionul nu vine din OneNote: doar text, fără „de verificat”
    assert {p.method for p in r.pages} == {"text-offline"} and r.manual() == [] and r.files


def test_publish_script_only_publishes_and_converts():
    for word in ("UpdatePageContent", "DeleteHierarchy", "CreateNewPage", "OpenHierarchy", "UpdateHierarchy",
                 "NavigateTo", "SyncHierarchy", "Remove-Item", "DeletePageContent", "MergeFiles"):
        assert word not in SCRIPT
    assert "$on.Publish(" in SCRIPT and "Documents.Open(" in SCRIPT


def test_settings_bot_out_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path / "data"))
    from pathlib import Path

    import docaudit

    clone = Path(docaudit.__file__).resolve().parents[1]
    assert update_settings({"bot_out_dir": str(tmp_path / "BotDDB")}).bot_out_dir
    for bad in ("relativ/folder", str(clone / "out")):
        with pytest.raises(ValueError):
            update_settings({"bot_out_dir": bad})
    with pytest.raises(ValueError):
        update_settings({"bot_level": "pagina"})
    with pytest.raises(ValueError):
        update_settings({"bot_max_mb": 0})
    assert Settings().bot_max_mb == 95


# ---------- serverul ----------

def _req(srv, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=60)
    headers = {"Host": f"127.0.0.1:{srv.server_address[1]}", "X-DocAudit-Token": srv.token}
    data = json.dumps(body).encode() if body is not None else None
    if data:
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=headers)
    r = conn.getresponse()
    out = r.status, json.loads(r.read() or b"{}")
    conn.close()
    return out


def test_server_bot_endpoints(ds):
    from docaudit.ui.server import DocAuditServer

    srv = DocAuditServer("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        status, plan = _req(srv, "GET", f"/api/bot/plan?ds={ds.name}")
        assert status == 200 and plan["offline"] and plan["compared"] and plan["last"] is None
        assert plan["counts"]["duplicate"] == 2 and plan["documents"]  # cea din eșantion + copia adăugată
        some = plan["documents"][0]["pages"][0]
        assert _req(srv, "POST", "/api/bot/override", {"ds": ds.name, "page": some, "value": "exclude"})[0] == 200
        status, plan2 = _req(srv, "GET", f"/api/bot/plan?ds={ds.name}")
        assert plan2["counts"]["excluded"] == 1
        assert _req(srv, "GET", f"/api/bot/plan?ds={ds.name}&level=pagina")[0] == 400
        status, r = _req(srv, "POST", "/api/bot/export", {"ds": ds.name, "wait": True})
        assert status == 200 and r["files"] and not r["cancelled"], r
        assert _req(srv, "GET", f"/api/bot/plan?ds={ds.name}")[1]["last"]["files"] == r["files"]
        assert plan["foreign"] == []
        status, mv = _req(srv, "POST", "/api/bot/move-foreign", {"ds": ds.name, "names": ["x.pdf"]})
        assert status == 200 and mv["moved"] == 0
        import sys

        if sys.platform != "win32":
            assert _req(srv, "POST", "/api/bot/pick-folder", {})[0] == 501
        status, o = _req(srv, "POST", "/api/bot/open", {"ds": ds.name})
        assert status == 200 and o["path"].endswith("out")
    finally:
        srv.shutdown()
        srv.server_close()


# ---------- cuprins, instrucțiuni, fișierele vechi ----------

def test_index_and_instructions_follow_changes(ds, tmp_path, fast):
    out = tmp_path / "bot"
    plan = build_plan(ds, level="section")
    r1 = export(ds, plan, out_dir=out, make_publisher=lambda: FakePublisher({}))
    assert r1.changes["first"] and (out / INDEX_FILE).is_file()
    text = (out / INSTRUCTIONS_FILE).read_text("utf-8")
    assert text == r1.instructions and r1.instructions_changed
    assert "Romanian or German" in text and INDEX_FILE in text and plan.documents[0]["name"] in text
    index = "".join(pg.extract_text() for pg in PdfReader(str(out / INDEX_FILE)).pages)
    assert "Primul export" in index

    # o pagină mutată (decizie „Mută…”) apare la „mutat”, ambele documente se reîncarcă
    pages = read_pages(ds)
    first_doc, other_doc = plan.documents[0], plan.documents[-1]
    moved = first_doc["pages"][0]
    target = next(p for p in pages if p.id == other_doc["pages"][0])
    Journal(ds).add(moved, "move", target=make_target(target.notebook, "/".join(target.section_path)))
    r2 = export(ds, build_plan(ds, level="section"), out_dir=out, make_publisher=lambda: FakePublisher({}))
    assert [m[1:] for m in r2.changes["moved"]] == [(first_doc["name"], other_doc["name"])]
    assert INDEX_FILE in r2.reupload and f"{other_doc['name']}.pdf" in r2.reupload
    assert "Mutat" in "".join(pg.extract_text() for pg in PdfReader(str(out / INDEX_FILE)).pages)

    # fără nimic nou: cuprinsul păstrează ultimele schimbări și nu cere reîncărcare
    r3 = export(ds, build_plan(ds, level="section"), out_dir=out, make_publisher=lambda: FakePublisher({}))
    assert r3.reupload == [] and not r3.instructions_changed
    assert "istoric" in "".join(p.name for p in (ds / "bot").iterdir())


def test_foreign_files_are_moved_aside_not_deleted(ds, tmp_path):
    out = tmp_path / "BotDDB"
    out.mkdir()
    (out / "Operations.pdf").write_bytes(b"vechi")
    (out / "Support_HOME_Part1.pdf").write_bytes(b"vechi")
    assert foreign_files(ds, out) == ["Operations.pdf", "Support_HOME_Part1.pdf"]
    export(ds, out_dir=out)
    assert foreign_files(ds, out) == ["Operations.pdf", "Support_HOME_Part1.pdf"]  # ale DocAudit nu apar
    assert move_foreign(ds, out, ["Operations.pdf", "nu-exista.pdf", "../x"]) is not None
    assert foreign_files(ds, out) == ["Support_HOME_Part1.pdf"]
    kept = next(out.glob("_vechi_*"))
    assert (kept / "Operations.pdf").read_bytes() == b"vechi"
    assert move_foreign(ds, out, []) is None
