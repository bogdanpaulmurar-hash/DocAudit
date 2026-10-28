"""Link-ul din browser al unui notebook → notebook-ul din OneNote desktop (fără rețea)."""

from pathlib import Path

import pytest

from docaudit.__main__ import main
from docaudit.extract.demo import DemoOneNote
from docaudit.extract.links import LinkError, match_link, parse_link
from docaudit.extract.onenote_xml import parse_hierarchy, parse_page

ONENOTE_FIX = Path(__file__).parent / "fixtures" / "onenote"
SITE = "https://exemplu.sharepoint.com/sites/Echipa"


@pytest.fixture(scope="module")
def tree():
    return parse_hierarchy(DemoOneNote().get_hierarchy_xml())


@pytest.mark.parametrize("link, notebook, section", [
    (f"{SITE}/Shared%20Documents/Proceduri%20IT", "Proceduri IT", None),
    (f"{SITE}/Shared%20Documents/Proceduri%20IT/?web=1", "Proceduri IT", None),
    ("https://EXEMPLU.sharepoint.com/:o:/r/sites/Echipa/Shared%20Documents/Proceduri%20IT?d=w123&csf=1&web=1",
     "Proceduri IT", None),
    (f"onenote:{SITE}/Shared%20Documents/Proceduri%20IT/Re%C8%9Bea.one#Instalare%20VPN&section-id={{A}}&page-id={{B}}&end",
     "Proceduri IT", "Proceduri IT/Rețea"),
    (f"{SITE}/_layouts/15/onenote.aspx?id=%2Fsites%2FEchipa%2FShared%20Documents%2FSuport%20Clien%C8%9Bi",
     "Suport Clienți", None),
    (f"{SITE}/_layouts/15/Doc.aspx?sourcedoc={{ABC}}&action=edit&wd=target%28Facilit%C4%83%C8%9Bi.one%7C{{X}}%2F%29",
     "Operațiuni", "Operațiuni/Facilități"),
])
def test_link_forms(tree, link, notebook, section):
    m = match_link(tree, parse_link(link))
    assert m is not None and m.notebook == notebook and m.section == section


def test_link_page_and_open_url():
    info = parse_link(f"onenote:{SITE}/Shared%20Documents/Proceduri%20IT/Re%C8%9Bea.one#Instalare%20VPN&page-id={{B}}")
    assert info.page == "Instalare VPN" and info.section == "Rețea"
    assert info.open_url == f"onenote:{SITE}/Shared%20Documents/Proceduri%20IT"


def test_link_not_open_or_not_a_link(tree):
    info = parse_link(f"{SITE}/Shared%20Documents/Alt%20Notebook")
    assert match_link(tree, info) is None and info.open_url.startswith("onenote:https://")
    share = parse_link("https://exemplu.sharepoint.com/:o:/g/personal/x/EaBcDeF?e=1")
    assert share.location is None and share.open_url is None and match_link(tree, share) is None
    for bad in ("", "notebook", "file:///C:/x", "javascript:alert(1)", "onenote:file:///x"):
        with pytest.raises(LinkError):
            parse_link(bad)


def test_hierarchy_and_page_in_2010_schema():
    xml = (ONENOTE_FIX / "hierarchy.xml").read_text("utf-8").replace("/2013/", "/2010/")
    h = parse_hierarchy(xml)
    assert [nb.name for nb in h.notebooks] == ["Proceduri IT", "Operațiuni"]
    assert h.notebooks[0].location == "C:\\Exemplu\\Proceduri\\"
    page_xml = (ONENOTE_FIX / "page_realistic.xml").read_text("utf-8")
    old, _ = parse_page(page_xml.replace("/2013/", "/2010/"), "N", ["S"])
    new, _ = parse_page(page_xml, "N", ["S"])
    assert old.text == new.text and old.title == new.title


def test_cli_tree_link(capsys):
    assert main(["tree", "--demo"]) == 0
    assert "Proceduri IT  [https://exemplu.sharepoint.com/" in capsys.readouterr().out
    assert main(["tree", "--demo", "--link", f"{SITE}/Shared%20Documents/Proceduri%20IT/Hardware.one"]) == 0
    assert "Proceduri IT/Hardware" in capsys.readouterr().out
    assert main(["tree", "--demo", "--link", f"{SITE}/Shared%20Documents/Altceva"]) == 1
    assert "onenote:https://" in capsys.readouterr().out


# ---------- „Verifică legătura cu OneNote” ----------

def test_diagnose_steps():
    from docaudit.extract.com import OneNoteError
    from docaudit.extract.diagnose import diagnose

    ok = diagnose(DemoOneNote, windows_checks=False)
    assert [c.key for c in ok] == ["com", "notebooks"] and all(c.ok for c in ok)
    assert ok[-1].detail.startswith("3: ")

    def broken():
        raise OneNoteError("OneNote desktop nu răspunde prin COM")

    bad = diagnose(broken, windows_checks=False)
    assert [(c.key, c.ok) for c in bad] == [("com", False), ("notebooks", None)] and "COM" in bad[0].detail

    class Empty:
        def get_hierarchy_xml(self):
            return '<one:Notebooks xmlns:one="http://schemas.microsoft.com/office/onenote/2013/onenote"/>'

    assert diagnose(Empty, windows_checks=False)[-1].ok is False


def test_diagnose_off_windows_and_cli(capsys, monkeypatch):
    import sys

    from docaudit.extract.diagnose import diagnose

    monkeypatch.setattr(sys, "platform", "linux")
    checks = diagnose()
    assert checks[0].key == "system" and checks[0].ok is False and all(c.ok is None for c in checks[1:])
    assert main(["diagnose", "--demo"]) == 0
    assert "[OK ]" in capsys.readouterr().out
    assert main(["diagnose"]) == 1
    assert "[NU ]" in capsys.readouterr().out
