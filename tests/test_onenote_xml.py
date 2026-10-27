"""Citirea XML-ului OneNote (ierarhie și pagină) și drumul dus-întors cu eșantionul."""

from pathlib import Path

import pytest

from docaudit.extract.onenote_xml import (
    ImageData,
    normalize_date,
    parse_hierarchy,
    parse_page,
    render_hierarchy_xml,
    render_page_xml,
)
from docaudit.model import validate_page_dict
from docaudit.sample import build_sample

FIX = Path(__file__).parent / "fixtures" / "onenote"


def test_hierarchy_structure_and_recycle_bin():
    h = parse_hierarchy((FIX / "hierarchy.xml").read_text("utf-8"))
    assert [nb.name for nb in h.notebooks] == ["Proceduri IT", "Operațiuni"]  # nickname are prioritate
    paths = [s.path for s in h.notebooks[0].sections]
    assert paths == [["Rețea"], ["Echipe", "Suport", "Ghiduri"], ["Arhivă"]]  # fără Coș
    titles = [p.title for p in h.pages()]
    assert "Pagină ștearsă" not in titles and "Din coș" not in titles
    vpn = h.pages()[0]
    assert (vpn.created, vpn.modified) == ("2024-01-10T08:00:00Z", "2025-04-30T12:34:56Z")
    assert h.pages()[1].level == 2


def test_realistic_page():
    page, images = parse_page((FIX / "page_realistic.xml").read_text("utf-8"), "Proceduri IT", ["Rețea"])
    assert page.title == "Instalare VPN"
    assert page.id == "{P1}{1}{E1}" and page.source.kind == "onenote_com"
    assert page.modified == "2025-04-30T12:34:56Z"
    assert [(b.type, b.text) for b in page.blocks] == [
        ("heading", "Pași"),
        ("para", "Descarcă clientul de pe portal."),
        ("list_item", "Rulează instalarea."),
        ("list_item", "Acceptă setările implicite."),
        ("list_item", "Setează portul 443."),
        ("table_row", "Server | vpn.example.test"),
        ("table_row", "Port | 443"),
        ("para", "Al doilea contur, mai jos pe pagină."),  # conturul de jos vine după
    ]
    assert page.blocks[0].level == 2 and page.blocks[3].level == 2
    assert page.text.splitlines()[2:5] == ["1. Rulează instalarea.", "- Acceptă setările implicite.",
                                          "2. Setează portul 443."]
    assert page.links == ["https://portal.example.test/software"]
    # aceeași imagine de două ori: o singură copie, două referințe; imaginea fără date e ignorată
    assert len(images) == 1 and len(page.images) == 2
    assert {i.ocr_text for i in page.images} == {None, "Conectat"}
    assert page.attachments[0].name == "config.xml" and page.attachments[0].sha256 == ""
    assert validate_page_dict(page.to_dict()) == []


@pytest.mark.parametrize("raw,expected", [
    ("2025-03-14T09:30:00.000Z", "2025-03-14T09:30:00Z"),
    ("2025-03-14T11:30:00+02:00", "2025-03-14T09:30:00Z"),
    ("2025-03-14T09:30:00", "2025-03-14T09:30:00Z"),
    (None, "1970-01-01T00:00:00Z"),
])
def test_normalize_date(raw, expected):
    assert normalize_date(raw) == expected


def test_sample_round_trip():
    """Fiecare pagină din eșantion, trecută prin XML OneNote și înapoi, rămâne la fel."""
    _, pages, images, _ = build_sample()
    imgs = {sha: ImageData("png", data) for sha, data in images.items()}
    for p in pages:
        back, found = parse_page(render_page_xml(p, imgs), p.notebook, p.section_path)
        assert (back.title, back.text, back.created, back.modified) == (p.title, p.text, p.created, p.modified)
        assert [(b.type, b.text) for b in back.blocks] == [(b.type, b.text) for b in p.blocks]
        assert [i.sha256 for i in back.images] == [i.sha256 for i in p.images]
        assert set(found) == {i.sha256 for i in p.images}


def test_special_characters_survive():
    _, pages, _, _ = build_sample()
    p = pages[0]
    p.title = "A < B & „C” > D"
    p.blocks[0].text = "<script>nu</script> & 5 > 3"
    back, _ = parse_page(render_page_xml(p), p.notebook, p.section_path)
    assert back.title == p.title and back.blocks[0].text == p.blocks[0].text


def test_hierarchy_round_trip():
    _, pages, _, _ = build_sample()
    h = parse_hierarchy(render_hierarchy_xml(pages))
    got = sorted((p.id, p.notebook, tuple(p.section_path), p.title, p.modified) for p in h.pages())
    exp = sorted((p.id, p.notebook, tuple(p.section_path), p.title, p.modified) for p in pages)
    assert got == exp


def test_update_xml_has_no_last_modified():
    _, pages, _, _ = build_sample()
    xml = render_page_xml(pages[0], page_id="{NEW}", for_update=True)
    assert "lastModifiedTime" not in xml and 'ID="{NEW}"' in xml
