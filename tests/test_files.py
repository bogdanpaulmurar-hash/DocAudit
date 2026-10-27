"""Importul din exporturi manuale (.mht, .docx)."""

import zipfile
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from docaudit.__main__ import main
from docaudit.extract.files import import_files, read_docx, read_mht
from docaudit.extract.selection import Selection
from docaudit.model import read_pages, validate_dataset

FIX = Path(__file__).parent / "fixtures"
PNG = next((FIX / "sample_v1" / "images").glob("*.png")).read_bytes()

HTML = """<html><head><title>Instalare VPN</title></head><body>
<h2>Pași</h2><p>Descarcă clientul de pe <a href="https://portal.example.test">portal</a>.</p>
<ol><li><p>Rulează instalarea.</p></li><li>Setează portul 443.</li></ol>
<table><tr><td>Server</td><td>vpn.example.test</td></tr></table>
<img src="cid:img1"></body></html>"""

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCX = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{W}"><w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Resetare parolă</w:t></w:r></w:p>
<w:p><w:r><w:t xml:space="preserve">Deschide portalul </w:t></w:r><w:r><w:t>parole.example.test.</w:t></w:r></w:p>
<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Alege parola nouă.</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Lungime</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>12</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
<w:p/></w:body></w:document>"""


def make_mht(path: Path) -> None:
    msg = MIMEMultipart("related")
    msg.attach(MIMEText(HTML, "html", "utf-8"))
    img = MIMEImage(PNG, "png")
    img.add_header("Content-ID", "<img1>")
    msg.attach(img)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(msg.as_bytes())


def make_docx(path: Path, title: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", DOCX)
        z.writestr("word/media/image1.png", PNG)
        if title:
            z.writestr("docProps/core.xml", f'<cp:coreProperties xmlns:cp="x" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{title}</dc:title></cp:coreProperties>')


def test_read_mht(tmp_path):
    make_mht(tmp_path / "a.mht")
    title, blocks, links, images = read_mht(tmp_path / "a.mht")
    assert title == "Instalare VPN"
    assert [(b.type, b.text) for b in blocks] == [
        ("heading", "Pași"), ("para", "Descarcă clientul de pe portal."),
        ("list_item", "Rulează instalarea."), ("list_item", "Setează portul 443."),
        ("table_row", "Server | vpn.example.test"),
    ]
    assert links == ["https://portal.example.test"]
    assert [i.ext for i in images.values()] == ["png"]


def test_read_docx(tmp_path):
    make_docx(tmp_path / "b.docx")
    title, blocks, _, images = read_docx(tmp_path / "b.docx")
    assert title == "Resetare parolă"  # primul titlu, când lipsește titlul documentului
    assert [(b.type, b.text) for b in blocks] == [
        ("para", "Deschide portalul parole.example.test."),
        ("list_item", "Alege parola nouă."),
        ("table_row", "Lungime | 12"),
    ]
    assert len(images) == 1
    make_docx(tmp_path / "c.docx", title="Titlu din proprietăți")
    assert read_docx(tmp_path / "c.docx")[0] == "Titlu din proprietăți"


def test_import_folder_layout(tmp_path):
    src, out = tmp_path / "export", tmp_path / "out"
    make_mht(src / "Proceduri IT" / "Rețea" / "vpn.mht")
    make_docx(src / "Proceduri IT" / "Conturi" / "Suport" / "parola.docx")
    make_docx(src / "Operațiuni" / "concediu.docx")
    make_docx(src / "liber.docx")
    (src / "ignorat.txt").write_text("x", encoding="utf-8")
    (src / "stricat.docx").write_bytes(b"nu e zip")

    report = import_files(src, out)
    assert report.fetched == 4 and len(report.errors) == 1
    assert validate_dataset(out) == []
    where = sorted((p.notebook, tuple(p.section_path)) for p in read_pages(out))
    assert where == [("Operațiuni", ("Export",)), ("Proceduri IT", ("Conturi", "Suport")),
                     ("Proceduri IT", ("Rețea",)), ("export", ("Export",))]
    vpn = next(p for p in read_pages(out) if p.title == "Instalare VPN")
    assert vpn.source.kind == "file_export" and vpn.text.splitlines()[2] == "1. Rulează instalarea."
    assert len(list((out / "images").iterdir())) == 1  # aceeași imagine peste tot

    assert import_files(src, out, Selection(notebooks=["Operațiuni"])).fetched == 1


def test_cli_import(tmp_path, capsys):
    make_mht(tmp_path / "src" / "Caiet" / "Sec" / "p.mht")
    assert main(["import-files", str(tmp_path / "src"), "--out", str(tmp_path / "out")]) == 0
    assert "1" in capsys.readouterr().out
