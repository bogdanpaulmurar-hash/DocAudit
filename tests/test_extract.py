"""Extragerea: selecție, profiluri, incremental, doar citire, fără rețea."""

import json

import pytest

from docaudit.__main__ import main
from docaudit.extract.check import compare_to_sample
from docaudit.extract.com import ReadOnlyOneNote
from docaudit.extract.demo import DemoOneNote
from docaudit.extract.run import extract_to_dataset
from docaudit.extract.selection import Selection, list_profiles, load_profile, save_profile
from docaudit.model import read_manifest, read_pages, validate_dataset
from docaudit.safety import no_network
from docaudit.testnotebook import archive_pages


def test_full_extract_matches_sample(tmp_path):
    with no_network():
        report = extract_to_dataset(DemoOneNote(), Selection(), tmp_path)
    assert (report.fetched, report.reused, report.errors) == (80, 0, [])
    assert validate_dataset(tmp_path) == []
    assert compare_to_sample(tmp_path) == []
    assert read_manifest(tmp_path).source.kind == "onenote_com"
    assert len(list((tmp_path / "images").iterdir())) == 5


def test_incremental(tmp_path):
    demo = DemoOneNote()
    extract_to_dataset(demo, Selection(), tmp_path)
    demo.page_requests.clear()
    report = extract_to_dataset(demo, Selection(), tmp_path)
    assert (report.fetched, report.reused) == (0, 80) and demo.page_requests == []

    changed = next(iter(demo.pages.values()))
    changed.modified = "2026-10-01T00:00:00Z"
    changed.blocks[0].text = "Text schimbat."
    gone = list(demo.pages)[-1]
    del demo.pages[gone]
    report = extract_to_dataset(demo, Selection(), tmp_path)
    assert (report.fetched, report.reused, report.removed) == (1, 78, 1)
    assert demo.page_requests == [changed.id]
    pages = {p.id: p for p in read_pages(tmp_path)}
    assert gone not in pages and pages[changed.id].blocks[0].text == "Text schimbat."

    report = extract_to_dataset(demo, Selection(), tmp_path, incremental=False)
    assert report.fetched == 79


def test_orphan_images_removed(tmp_path):
    demo = DemoOneNote()
    extract_to_dataset(demo, Selection(), tmp_path)
    extract_to_dataset(demo, Selection(notebooks=["Operațiuni"]), tmp_path)
    used = {i.sha256 for p in read_pages(tmp_path) for i in p.images}
    assert {f.stem for f in (tmp_path / "images").iterdir()} == used


@pytest.mark.parametrize("sel,count", [
    (Selection(), 80),
    (Selection(notebooks=["Operațiuni"]), 35),
    (Selection(sections=["Proceduri IT/Rețea"]), 5),
    (Selection(sections=["Proceduri IT/Rețea"], notebooks=["Operațiuni"]), 40),
    (Selection(exclude_sections=["rețea"]), 75),  # fără diferență de majuscule
])
def test_selection(tmp_path, sel, count):
    report = extract_to_dataset(DemoOneNote(), sel, tmp_path)
    assert report.total == count and report.skipped == 80 - count


def test_selection_by_page_id(tmp_path):
    demo = DemoOneNote()
    ids = list(demo.pages)[:3]
    report = extract_to_dataset(demo, Selection(pages=ids), tmp_path)
    assert sorted(p.id for p in read_pages(tmp_path)) == sorted(ids) and report.total == 3


def test_archive_section_excluded_by_default(tmp_path):
    arch = archive_pages()
    for i, p in enumerate(arch):
        p.id, p.notebook = f"arch-{i}", "Proceduri IT"
    demo = DemoOneNote()
    demo.pages.update({p.id: p for p in arch})
    assert extract_to_dataset(demo, Selection(), tmp_path).total == 80
    assert extract_to_dataset(demo, Selection(exclude_sections=[]), tmp_path).total == 82


def test_broken_page_does_not_stop_extraction(tmp_path):
    class Broken(DemoOneNote):
        def get_page_xml(self, page_id):
            if page_id == "sample-p007":
                return "<nu e xml"
            return super().get_page_xml(page_id)

    report = extract_to_dataset(Broken(), Selection(), tmp_path)
    assert report.fetched == 79 and len(report.errors) == 1
    assert validate_dataset(tmp_path) == []


def test_profiles(tmp_path):
    sel = Selection(notebooks=["Operațiuni"], sections=["Proceduri IT/Rețea"], exclude_sections=["Arhivă", "Note"])
    path = save_profile(tmp_path, "Proceduri / IT: rețea?", sel)
    assert path.parent == tmp_path and "/" not in path.name.replace(".json", "")
    assert load_profile(tmp_path, "Proceduri / IT: rețea?") == sel
    assert list_profiles(tmp_path) == ["Proceduri / IT: rețea?"]
    assert list_profiles(tmp_path / "nu-exista") == []


def test_com_client_is_read_only():
    public = {n for n in vars(ReadOnlyOneNote) if not n.startswith("_")}
    assert public == {"get_hierarchy_xml", "get_page_xml"}


def test_cli_extract_tree_profile_check(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path))
    with no_network():
        assert main(["tree", "--demo"]) == 0
        assert "Proceduri IT" in capsys.readouterr().out
        assert main(["profile", "save", "op", "--notebook", "Operațiuni"]) == 0
        assert main(["profile", "list"]) == 0
        assert capsys.readouterr().out.strip().endswith("op")
        assert main(["extract", "--demo", "--profile", "op"]) == 0
        assert len(read_pages(tmp_path / "op")) == 35
        assert main(["extract", "--demo"]) == 0
        assert main(["check-sample", str(tmp_path / "demo")]) == 0
    saved = json.loads((tmp_path / "profiles" / "op.json").read_text("utf-8"))
    assert saved["selection"]["notebooks"] == ["Operațiuni"]


def test_cli_without_onenote(monkeypatch, capsys):
    """Fără pywin32 (Linux, CI), comanda spune clar că OneNote lipsește."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name in ("pythoncom", "win32com.client", "win32com"):
            raise ImportError(name)
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert main(["tree"]) == 2
    assert "OneNote" in capsys.readouterr().out
