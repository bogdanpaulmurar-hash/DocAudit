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
