"""Etapele 6–8: jurnalul deciziilor, raportul, aplicarea în OneNote (pe un OneNote fals), serverul local, iconița."""

import http.client
import json
import shutil
import struct
import threading

import pytest

from docaudit.__main__ import main
from docaudit.apply.run import WriteDisabled, apply, plan, restore, writer_for
from docaudit.apply.writer import FakeOneNote
from docaudit.apply.xmlops import copy_page_xml, has_prefix, title_html_of, title_of, title_update_xml
from docaudit.compare.run import run_compare
from docaudit.decisions import Journal
from docaudit.extract.demo import DemoOneNote
from docaudit.extract.onenote_xml import parse_hierarchy, parse_page
from docaudit.extract.run import extract_to_dataset
from docaudit.extract.selection import Selection
from docaudit.group.run import run_grouping
from docaudit.icon import ico, png
from docaudit.report import build_state, render
from docaudit.settings import Settings, load_settings, update_settings
from docaudit.ui.server import DocAuditServer


@pytest.fixture
def data(tmp_path, monkeypatch):
    """O extragere demo analizată, în folderul de date al testului."""
    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("DOCAUDIT_LANG", "ro")
    folder = tmp_path / "data" / "demo"
    extract_to_dataset(DemoOneNote(), Selection(), folder, source_label="demo (eșantion fictiv)")
    run_grouping(folder)
    run_compare(folder)
    return folder


def _where(fake: FakeOneNote) -> dict:
    out = {}
    for nb in parse_hierarchy(fake.get_hierarchy_xml()).notebooks:
        for s in nb.sections:
            for p in s.pages:
                out[p.id] = ("/".join(s.path), p.title)
    return out


# ---------- jurnal și raport ----------

def test_journal_current_undo_and_pending(data):
    j = Journal(data)
    a = j.add("sample-p024", "archive", note="veche")
    j.add("sample-p024", "mark_stale")
    j.add("sample-p005", "reference")
    assert j.current()["sample-p024"].action == "mark_stale"  # ultima decizie câștigă
    assert [d.action for d in j.pending()] == ["mark_stale"]
    last = j.current()["sample-p024"]
    assert j.undo(last.id) and not j.undo(last.id)
    assert j.current()["sample-p024"].id == a.id  # se revine la decizia anterioară
    with pytest.raises(ValueError):
        j.add("x", "sterge")
    with pytest.raises(ValueError):
        j.add("x", "ignore")
    assert len(j.history()) == 3


def test_state_and_reports(data):
    j = Journal(data)
    st = build_state(data)
    group = next(g for g in st["groups"] if any(p["id"] == "sample-p039" for p in g["pages"]))
    conflict = next(f for f in group["findings"] if f["kind"] == "value_conflict" and "8443" in f["text"])
    j.add("sample-p039", "ignore", finding=conflict["key"])
    j.add("sample-p024", "archive")
    st = build_state(data)
    group = next(g for g in st["groups"] if g["id"] == group["id"])
    assert next(f for f in group["findings"] if f["key"] == conflict["key"])["ignored"]
    assert [d["page_id"] for d in st["pending"]] == ["sample-p024"]
    csv_text = render(st, "csv", "ro")
    assert csv_text.startswith("﻿Grup;Gravitate;") and "8443" in csv_text and "ignorată" in csv_text
    md = render(st, "md", "en")
    assert md.startswith("# DocAudit report — demo") and "| Group |" in md
    html = render(st, "html", "de")
    assert "<table>" in html and "DocAudit-Bericht" in html
    # textul paginilor ajunge în HTML doar escapat
    assert "<script" not in html.lower()


# ---------- Etapa 7: aplicare, pe OneNote-ul fals ----------

def test_xml_copy_and_title():
    fake_page = DemoOneNote().get_page_xml("sample-p005")
    copy = copy_page_xml(fake_page, "{NEW}", note="Mutat din: Rețea, 27.10.2026, motiv: test")
    page, _ = parse_page(copy, "NB", ["Arhivă"])
    assert page.id == "{NEW}" and page.blocks[0].text.startswith("Mutat din: Rețea")
    assert page.title == title_of(fake_page)
    partial, old = title_update_xml(fake_page, "[ÎNVECHIT] " + title_html_of(fake_page))
    assert "Outline" not in partial and old == title_html_of(fake_page)
    assert has_prefix("[ÎNVECHIT] Titlu", "[ÎNVECHIT] ") and not has_prefix("Titlu", "[ÎNVECHIT] ")


def test_apply_needs_write_enabled(data):
    Journal(data).add("sample-p024", "archive")
    writer = writer_for(data)
    items = plan(data, writer, load_settings())
    assert [(i.page_id, i.status) for i in items] == [("sample-p024", "ready")]
    with pytest.raises(WriteDisabled):
        apply(data, writer, Settings(write_enabled=False), [items[0].decision_id])
    assert writer.calls == []  # previzualizarea nu scrie nimic


def test_archive_mark_and_restore(data, tmp_path):
    j = Journal(data)
    arch = j.add("sample-p024", "archive", note="versiune veche")
    stale = j.add("sample-p027", "mark_stale")
    j.add("sample-p005", "reference")  # referința nu scrie în OneNote
    settings = Settings(write_enabled=True)
    writer = writer_for(data)
    before = _where(writer)
    items = plan(data, writer, settings)
    assert {i.decision_id for i in items} == {arch.id, stale.id}
    result = apply(data, writer, settings, [arch.id, stale.id])
    assert len(result.done) == 2 and not result.errors

    after = _where(writer)
    assert "sample-p024" not in after  # originalul e în Coș
    archived = [pid for pid, (sec, title) in after.items() if sec == "Arhivă"]
    assert len(archived) == 1 and after[archived[0]][1] == before["sample-p024"][1]
    page, _ = parse_page(writer.get_page_xml(archived[0]), "", [])
    assert page.blocks[0].text.startswith(f"Mutat din: {before['sample-p024'][0]}") and "versiune veche" in page.blocks[0].text
    assert after["sample-p027"][1] == "[ÎNVECHIT] " + before["sample-p027"][1]
    # copiile de siguranță există înainte de scriere
    backups = list((tmp_path / "data" / "_backups").rglob("*.xml"))
    assert len(backups) == 2
    assert plan(data, writer, settings) == []  # nimic rămas de aplicat

    for row in Journal(data).applied():
        restore(data, writer, settings, row["id"])
    restored = _where(writer)
    assert not [pid for pid, (sec, _) in restored.items() if sec == "Arhivă"]
    assert (before["sample-p024"][0], before["sample-p024"][1]) in restored.values()
    assert restored["sample-p027"][1] == before["sample-p027"][1]
    with pytest.raises(ValueError):
        restore(data, writer, settings, Journal(data).applied()[0]["id"])


def test_changed_page_is_skipped(data):
    j = Journal(data)
    d = j.add("sample-p027", "mark_stale")
    writer = writer_for(data)
    # cineva editează pagina în OneNote după extragere
    _, _, page = writer._find("sample-p027")
    page["lastModifiedTime"] = "2026-10-27T23:59:00Z"
    writer.save()
    items = plan(data, writer, Settings(write_enabled=True))
    assert items[0].status == "skip" and items[0].reason == "changed"
    result = apply(data, writer, Settings(write_enabled=True), [d.id])
    assert not result.done and result.skipped
    assert "update_page" not in writer.calls


def test_apply_refuses_file_imports(tmp_path, monkeypatch, fixture_dir):
    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path))
    folder = tmp_path / "imp"
    shutil.copytree(fixture_dir, folder)
    manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
    manifest["source"]["kind"] = "file_export"
    (folder / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    with pytest.raises(WriteDisabled):
        writer_for(folder)


def test_cli_apply_preview_then_yes(data, capsys):
    Journal(data).add("sample-p024", "archive")
    assert main(["apply", str(data)]) == 0
    assert "Previzualizare" in capsys.readouterr().out
    assert main(["apply", str(data), "--yes"]) == 2  # mod doar citire
    update_settings({"write_enabled": True})
    assert main(["apply", str(data), "--yes"]) == 0
    assert "1 aplicate" in capsys.readouterr().out
    assert main(["report", str(data), "--format", "md"]) == 0
    assert (data / "raport.md").is_file()


# ---------- setări ----------

def test_settings_defaults_and_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path))
    s = load_settings()
    assert s.write_enabled is False and s.archive_section == "Arhivă"  # doar citire implicit
    assert update_settings({"threshold": 0.7, "necunoscut": 1}).threshold == 0.7
    for bad in ({"lang": "fr"}, {"threshold": 2}, {"archive_section": "a/b"}, {"port": 80}):
        with pytest.raises(ValueError):
            update_settings(bad)
    assert load_settings().threshold == 0.7


# ---------- serverul local ----------

@pytest.fixture
def server(data):
    srv = DocAuditServer("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _req(srv, method, path, body=None, token=True, host=None, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    headers = {"Host": host or f"127.0.0.1:{srv.server_address[1]}"}
    if token:
        headers["X-DocAudit-Token"] = srv.token
    if origin:
        headers["Origin"] = origin
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=headers)
    r = conn.getresponse()
    raw = r.read()
    conn.close()
    try:
        return r.status, json.loads(raw), r
    except ValueError:
        return r.status, raw, r


def test_server_only_on_loopback():
    with pytest.raises(ValueError):
        DocAuditServer("0.0.0.0", 0)


def test_server_security(server):
    status, body, r = _req(server, "GET", "/", token=False)
    assert status == 200 and server.token.encode() in body
    assert "frame-ancestors 'none'" in r.getheader("Content-Security-Policy")
    assert r.getheader("Access-Control-Allow-Origin") is None
    assert _req(server, "GET", "/api/info", token=False)[0] == 403
    assert _req(server, "GET", "/api/info", host="evil.example")[0] == 403  # DNS rebinding
    assert _req(server, "POST", "/api/settings", {"write_enabled": True}, origin="https://evil.example")[0] == 403
    assert _req(server, "POST", "/api/settings", {"write_enabled": True}, token=False)[0] == 403
    assert load_settings().write_enabled is False
    assert _req(server, "GET", "/api/state?ds=../etc")[0] == 400
    assert _req(server, "GET", "/api/image?ds=demo&sha=../../x")[0] == 404


def test_server_full_flow(server, data):
    status, info, _ = _req(server, "GET", "/api/info")
    assert status == 200 and info["datasets"][0]["name"] == "demo" and not info["settings"]["write_enabled"]
    texts = _req(server, "GET", "/api/texts?lang=de")[1]
    assert texts["ui.tab.groups"] == "Gruppen"
    state = _req(server, "GET", "/api/state?ds=demo&lang=en")[1]
    assert len(state["groups"]) == 15 and state["compared"]
    page = _req(server, "GET", "/api/page?ds=demo&id=sample-p039")[1]
    assert "8443" in page["text"]
    sha = next(i["sha256"] for g in state["groups"] for p in g["pages"]
               for i in _req(server, "GET", f"/api/page?ds=demo&id={p['id']}")[1]["images"])
    status, img, r = _req(server, "GET", f"/api/image?ds=demo&sha={sha}&t={server.token}", token=False)
    assert status == 200 and img[:4] == b"\x89PNG"

    d = _req(server, "POST", "/api/decision", {"ds": "demo", "page": "sample-p024", "action": "archive"})[1]
    assert _req(server, "POST", "/api/decision", {"ds": "demo", "page": "x", "action": "delete"})[0] == 400
    plan_ = _req(server, "GET", "/api/plan?ds=demo")[1]
    assert plan_["items"][0]["status"] == "ready" and not plan_["write_enabled"]
    assert _req(server, "POST", "/api/apply", {"ds": "demo", "ids": [d["id"]], "confirm": True})[0] == 403
    assert _req(server, "POST", "/api/settings", {"write_enabled": True})[0] == 200
    assert _req(server, "POST", "/api/apply", {"ds": "demo", "ids": [d["id"]]})[0] == 400  # fără confirmare
    res = _req(server, "POST", "/api/apply", {"ds": "demo", "ids": [d["id"]], "confirm": True})[1]
    assert len(res["done"]) == 1
    applied = _req(server, "GET", "/api/applied?ds=demo")[1]["items"]
    assert _req(server, "POST", "/api/undo", {"ds": "demo", "id": d["id"]})[0] == 409  # aplicată: doar restaurare
    assert _req(server, "POST", "/api/restore", {"ds": "demo", "id": applied[0]["id"]})[0] == 200

    status, report, r = _req(server, "GET", "/api/report?ds=demo&format=csv&lang=ro")
    assert status == 200 and "attachment" in r.getheader("Content-Disposition")
    detach = _req(server, "POST", "/api/decision", {"ds": "demo", "page": "sample-p039", "action": "not_in_group"})
    assert detach[0] == 200 and (data / "group_overrides.json").is_file()
    analyzed = _req(server, "POST", "/api/analyze", {"ds": "demo", "threshold": 0.6})[1]
    assert analyzed["groups"] >= 15


def test_server_extract_demo(server, tmp_path):
    tree = _req(server, "GET", "/api/tree?demo=1")[1]
    assert len(tree["notebooks"]) == 3
    r = _req(server, "POST", "/api/extract", {"demo": True, "out": "doar-retea", "sections": ["Proceduri IT/Rețea"]})[1]
    assert r["name"] == "doar-retea" and 0 < r["total"] < 80
    assert _req(server, "POST", "/api/extract", {"demo": True, "out": "../afara"})[0] == 400
    assert tree["notebooks"][0]["location"].startswith("https://exemplu.sharepoint.com/")
    link = "https://exemplu.sharepoint.com/sites/Echipa/Shared%20Documents/Proceduri%20IT/Re%C8%9Bea.one"
    found = _req(server, "POST", "/api/link", {"demo": True, "link": link})[1]
    assert found["found"] and found["notebook"] == "Proceduri IT" and found["section"] == "Proceduri IT/Rețea"
    missing = _req(server, "POST", "/api/link", {"demo": True, "link": link.replace("Proceduri%20IT", "Altul")})[1]
    assert not missing["found"] and missing["open_url"].startswith("onenote:https://exemplu.sharepoint.com/")
    assert _req(server, "POST", "/api/link", {"demo": True, "link": "javascript:alert(1)"})[0] == 400


# ---------- iconița ----------

def test_icon_files(tmp_path):
    data = png(32)
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", data[16:24]) == (32, 32)
    icon = ico((16, 32))
    assert struct.unpack("<HHH", icon[:6]) == (0, 1, 2)
    assert main(["make-icon", str(tmp_path / "i")]) == 0
    assert (tmp_path / "i" / "docaudit.ico").stat().st_size > 100
