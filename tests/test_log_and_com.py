"""Legătura COM (varianta de parametri), extragerea pe notebook-uri mari și logul tehnic."""

import logging
from pathlib import Path

import pytest

from docaudit import log
from docaudit.extract.connect import ComCaller, arg_variants
from docaudit.extract.demo import DemoOneNote
from docaudit.extract.run import extract_to_dataset
from docaudit.extract.selection import Selection
from docaudit.model import read_manifest, read_pages

MISSING = object()


class MakepyLike:
    """Legarea din biblioteca de tipuri: fără loc pentru [out] (ca la laptopul de lucru)."""

    def GetHierarchy(self, start="", scope=0, schema=2):
        return "<one:Notebooks xmlns:one='x'/>"

    def GetPageContent(self, page_id, info=0, schema=2):
        assert info is not MISSING, "parametrii mutați: pagina ar pica"
        return f"<page id='{page_id}' info='{info}' schema='{schema}'/>"

    def CreateNewPage(self, section_id, style=0):
        self.created = getattr(self, "created", 0) + 1
        return "{new}"


class DynamicLike:
    """Legarea dinamică: vrea locul pentru [out]."""

    def GetPageContent(self, page_id, out, info=0, schema=2):
        assert out is MISSING
        return ("ignored", f"<page id='{page_id}' info='{info}'/>")

    def CreateNewPage(self, section_id, out, style=0):
        raise RuntimeError("COM: secțiune blocată")


def test_arg_variants_order():
    v = arg_variants(("p",), (1, 2), MISSING)
    assert v[:2] == [("p", MISSING, 1, 2), ("p", 1, 2)]
    assert ("p",) in v and len(v) == len(set(map(id, v)))


def test_com_caller_makepy_and_dynamic():
    call = ComCaller(MakepyLike(), MISSING)
    assert "info='1'" in call("GetPageContent", ("x",), (1, 2), xml=True)
    assert call._chosen["GetPageContent"] == 1  # ținută minte pentru paginile următoare
    assert call("GetHierarchy", ("", 4), (2,), xml=True).startswith("<")
    dyn = ComCaller(DynamicLike(), MISSING)
    assert "info='1'" in dyn("GetPageContent", ("x",), (1, 2), xml=True)


def test_com_caller_write_is_not_repeated():
    app = MakepyLike()
    assert ComCaller(app, MISSING)("CreateNewPage", ("s",), (0,), write=True) == "{new}"
    assert app.created == 1
    with pytest.raises(RuntimeError, match="blocată"):  # o eroare COM la scriere nu se reîncearcă altfel
        ComCaller(DynamicLike(), MISSING)("CreateNewPage", ("s",), (0,), write=True)


class BrokenPages(DemoOneNote):
    def get_page_xml(self, page_id: str) -> str:
        raise RuntimeError("GetPageContent: 0x80042014")


def test_extract_stops_when_every_page_fails(tmp_path):
    report = extract_to_dataset(BrokenPages(), Selection(), tmp_path / "x", abort_after=3)
    assert report.aborted.startswith("RuntimeError") and len(report.errors) == 3 and report.total == 0


def test_extract_cancel_keeps_what_was_read(tmp_path):
    out = tmp_path / "mare"
    calls = {"n": 0}

    def cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 30

    report = extract_to_dataset(DemoOneNote(), Selection(), out, cancel=cancel, checkpoint_every=10)
    assert report.cancelled and report.fetched == 30
    assert read_manifest(out).page_count == 30
    again = extract_to_dataset(DemoOneNote(), Selection(), out)  # continuă: refolosește cele 30
    assert again.reused == 30 and again.total == 80 and len(read_pages(out)) == 80


def test_extract_checkpoint_written_during_run(tmp_path):
    out = tmp_path / "pas"
    seen = []

    def progress(n, total, _title):
        if n == 25:
            seen.append(read_manifest(out).page_count)

    extract_to_dataset(DemoOneNote(), Selection(), out, progress=progress, checkpoint_every=10)
    assert seen == [20]


def test_log_local_shared_and_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("DOCAUDIT_LOG_SHARE", raising=False)
    shared = tmp_path / "drive" / "logs"
    try:
        info = log.setup(share=True, custom_dir=str(shared), force=True)
        assert info["shared"] and Path(info["shared"]).parent == shared
        log.get("test").info("cale %s", str(Path.home() / "secret.txt"))
        for h in logging.getLogger("docaudit").handlers:
            h.flush()
        text = Path(info["shared"]).read_text("utf-8")
        assert "secret.txt" in text and str(Path.home()) not in text
        assert Path(info["local"]).read_text("utf-8") == text
        assert any("secret.txt" in line for line in log.tail())
        assert log.machine_label().startswith("pc-") and len(log.machine_label()) == 9
    finally:
        log.setup(share=False, custom_dir="", force=True)
        for h in logging.getLogger("docaudit").handlers:
            h.close()


def test_log_never_has_page_titles(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path / "data"))
    try:
        info = log.setup(share=False, custom_dir="", force=True)
        extract_to_dataset(BrokenPages(), Selection(), tmp_path / "x", abort_after=2)
        extract_to_dataset(DemoOneNote(), Selection(), tmp_path / "y")
        for h in logging.getLogger("docaudit").handlers:
            h.flush()
        text = Path(info["local"]).read_text("utf-8")
        titles = {p.title for p in read_pages(tmp_path / "y")} | {p.notebook for p in read_pages(tmp_path / "y")}
        assert "Extragere gata" in text and not [t for t in titles if t in text]
    finally:
        log.setup(share=False, custom_dir="", force=True)
        for h in logging.getLogger("docaudit").handlers:
            h.close()


class FakeComError(Exception):
    """Ca pywin32 com_error: primul argument e codul COM."""


class CrashingOneNote:
    """GetPageContent: prima dată „RPC server unavailable” (OneNote a căzut), apoi merge."""

    def __init__(self, crashes: int, crash_with_images_only: bool = False) -> None:
        self.crashes, self.with_images_only = crashes, crash_with_images_only
        self.calls = []

    def GetPageContent(self, page_id, info=0, schema=2):
        self.calls.append(info)
        if self.crashes and (not self.with_images_only or info == 1):
            self.crashes -= 1
            raise FakeComError(-2147023174, "The RPC server is unavailable.", None, None)
        return f"<page info='{info}'/>"


def test_com_caller_stops_on_rpc_error():
    from docaudit.extract.connect import OneNoteGone

    app = CrashingOneNote(crashes=1)
    with pytest.raises(OneNoteGone, match="0x800706BA"):
        ComCaller(app, MISSING)("GetPageContent", ("p",), (1, 2), xml=True)
    assert len(app.calls) == 1  # nu mai încearcă celelalte 5 variante pe un OneNote căzut


def _readonly(app, monkeypatch, tmp_path):
    from docaudit.extract import com

    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(com, "PAUSE", 0)
    monkeypatch.setattr(com, "RECOVER", 0)
    monkeypatch.setattr(com.time, "sleep", lambda s: None)
    ro = com.ReadOnlyOneNote.__new__(com.ReadOnlyOneNote)
    ro._missing, ro.without_images, ro._how, ro._problems = MISSING, 0, "test", []
    ro.reconnects = 0
    ro._init_ways()

    def reconnect():
        ro.reconnects += 1
        ro._call = ComCaller(app, MISSING)

    ro._call = ComCaller(app, MISSING)
    ro._connect = reconnect
    return ro


def test_readonly_page_crash_after_way_works(monkeypatch, tmp_path):
    app = CrashingOneNote(crashes=0)
    ro = _readonly(app, monkeypatch, tmp_path)
    assert ro.get_page_xml("p1") == "<page info='1'/>"
    app.crashes, app.with_images_only = 1, True
    assert ro.get_page_xml("p2") == "<page info='0'/>" and ro.reconnects == 1 and ro.without_images == 1


def test_readonly_first_page_crash_with_no_other_way_stops(monkeypatch, tmp_path):
    from docaudit.extract import com, psbridge

    monkeypatch.setattr(psbridge.shutil, "which", lambda name: None)  # fără PowerShell
    ro = _readonly(CrashingOneNote(crashes=2), monkeypatch, tmp_path)  # cade cu și fără imagini
    with pytest.raises(com.OneNoteError, match="toate căile") as e:
        ro.get_page_xml("p")
    assert e.value.fatal and com.load_read_memory()["crashed"] == ["pywin32"]


# ---------- căile de citire a paginilor (OneNote cade la fiecare pagină prin pywin32) ----------

def _gone(code=-2147023170):
    from docaudit.extract.connect import OneNoteGone

    return OneNoteGone("GetPageContent", code, False)


def _ways(monkeypatch, tmp_path, behaviour):
    """ReadOnlyOneNote cu căi false: behaviour[cale] = funcție (page_id, info) sau excepție la pornire."""
    from docaudit.extract import com

    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(com, "PAUSE", 0)
    monkeypatch.setattr(com, "RECOVER", 0)
    ro = com.ReadOnlyOneNote.__new__(com.ReadOnlyOneNote)
    ro._missing, ro.without_images = MISSING, 0
    ro._init_ways()
    started = []

    def reader(way):
        if way not in ro._readers:
            started.append(way)
            b = behaviour.get(way, com._Unusable("lipsește"))
            if isinstance(b, Exception):
                raise b
            ro._readers[way] = b
        return ro._readers[way]

    ro._reader = reader
    return ro, started


def test_page_way_switches_after_crash_and_is_remembered(monkeypatch, tmp_path):
    from docaudit.extract import com

    calls = []

    def powershell(pid, info):
        calls.append(("powershell", pid, info))
        raise _gone()

    def pywin32(pid, info):
        calls.append(("pywin32", pid, info))
        return f"<page id='{pid}' info='{info}'/>"

    ro, started = _ways(monkeypatch, tmp_path, {"powershell": powershell, "pywin32": pywin32})
    assert ro.get_page_xml("a") == "<page id='a' info='1'/>"
    assert ro.get_page_xml("b").startswith("<page id='b'")
    assert calls == [("powershell", "a", 1), ("powershell", "a", 0),  # cu imagini, apoi o dată fără
                     ("pywin32", "a", 1), ("pywin32", "b", 1)]
    assert com.load_read_memory() == {"crashed": ["powershell"], "ok": "pywin32"}
    ro2, started2 = _ways(monkeypatch, tmp_path, {"powershell": powershell, "pywin32": pywin32})
    ro2.get_page_xml("c")
    assert started2 == ["pywin32"] and len(calls) == 5  # rularea următoare nu mai face OneNote să cadă


def test_first_page_only_without_images_keeps_the_way(monkeypatch, tmp_path):
    def powershell(pid, info):
        if info == 1:
            raise _gone()
        return "<page info='0'/>"

    ro, started = _ways(monkeypatch, tmp_path, {"powershell": powershell})
    assert ro.get_page_xml("a") == "<page info='0'/>" and ro.without_images == 1 and ro._way == "powershell"


def test_page_way_unusable_is_skipped_without_crash(monkeypatch, tmp_path):
    from docaudit.extract import com

    ro, started = _ways(monkeypatch, tmp_path, {
        "powershell": com._Unusable("PowerShell nu a fost găsit"),
        "pywin32": lambda pid, info: (_ for _ in ()).throw(AttributeError("GetPageContent")),
        "comtypes": lambda pid, info: "<page/>"})
    assert ro.get_page_xml("a") == "<page/>"
    assert started == ["powershell", "pywin32", "comtypes"]
    assert com.load_read_memory() == {"ok": "comtypes"}  # nimic marcat „cade”


def test_all_ways_crash_stops_extraction_at_first_page(monkeypatch, tmp_path):
    from docaudit.extract import com

    def crash(pid, info):
        raise _gone()

    ro, started = _ways(monkeypatch, tmp_path, {w: crash for w in com.WAYS})
    hier = DemoOneNote()
    ro.get_hierarchy_xml = hier.get_hierarchy_xml
    report = extract_to_dataset(ro, Selection(), tmp_path / "x")
    assert report.aborted and "toate căile" in report.aborted and len(report.errors) == 1
    assert list(dict.fromkeys(started)) == list(com.WAYS) and len(started) == 2 * len(com.WAYS)  # cu și fără imagini, apoi stop


def test_page_that_crashes_after_way_works_is_read_without_images(monkeypatch, tmp_path):
    seen = []

    def pywin32(pid, info):
        seen.append((pid, info))
        if pid == "rea" and info == 1:
            raise _gone()
        return f"<page info='{info}'/>"

    ro, _ = _ways(monkeypatch, tmp_path, {"pywin32": pywin32})
    assert ro.get_page_xml("buna") == "<page info='1'/>"
    assert ro.get_page_xml("rea") == "<page info='0'/>" and ro.without_images == 1
    assert ro._way == "pywin32"  # calea rămâne aceeași: doar pagina era problema


def test_powershell_reply_parsing():
    import base64

    from docaudit.extract.connect import OneNoteGone
    from docaudit.extract.psbridge import SCRIPT, parse_reply

    xml = "<one:Page>ăîșț ü</one:Page>"
    assert parse_reply("OK " + base64.b64encode(xml.encode()).decode() + "\r\n") == xml
    with pytest.raises(OneNoteGone):
        parse_reply("ERR -2147023170 The remote procedure call failed.")
    with pytest.raises(OneNoteGone):
        parse_reply("")  # PowerShell s-a oprit fără răspuns
    with pytest.raises(RuntimeError, match="0x80042014"):
        parse_reply("ERR -2147213292 page not found")
    for word in ("UpdatePageContent", "DeleteHierarchy", "UpdateHierarchy", "Publish", "CreateNewPage"):
        assert word not in SCRIPT  # scriptul doar citește
