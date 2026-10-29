"""Titlu nou și text adăugat în pagină, la decizie (aplicate în OneNote-ul fals)."""

import pytest

from docaudit.apply.run import apply, plan, restore, writer_for
from docaudit.apply.xmlops import add_text_xml, added_paragraph_ids, object_ids, title_of
from docaudit.decisions import Journal
from docaudit.extract.onenote_xml import parse_page
from docaudit.report import build_state
from docaudit.settings import Settings

from test_app import _req, _where, data, server  # noqa: F401 - fixturile comune


def _text(writer, pid):
    page, _ = parse_page(writer.get_page_xml(pid), "", [])
    return [b.text for b in page.blocks]


def test_journal_edits_validation_and_pending(data):  # noqa: F811
    j = Journal(data)
    with pytest.raises(ValueError):
        j.add("sample-p027", "rename", target="   ")
    with pytest.raises(ValueError):
        j.add("sample-p027", "add_text", target="top\t  ")
    j.add("sample-p027", "rename", target="Primul  titlu ")
    r = j.add("sample-p027", "rename", target="Titlu nou")
    a = j.add("sample-p027", "add_text", target="end\tRând adăugat")
    b = j.add("sample-p027", "add_text", target="fără poziție")  # poziția lipsă = sus
    j.add("sample-p027", "reference")
    assert j.current()["sample-p027"].action == "reference"  # editările nu înlocuiesc decizia
    e = j.edits()["sample-p027"]
    assert e["rename"].id == r.id and [d.id for d in e["add_text"]] == [a.id, b.id]
    assert b.target == "top\tfără poziție"
    assert {d.id for d in j.pending()} == {r.id, a.id, b.id}
    page = next(p for g in build_state(data)["groups"] for p in g["pages"] if p["id"] == "sample-p027")
    assert page["rename"]["title"] == "Titlu nou"
    assert [(x["at"], x["text"]) for x in page["added_texts"]] == [("end", "Rând adăugat"), ("top", "fără poziție")]


def test_add_text_xml_keeps_existing_ids(fixture_dir):
    xml = (fixture_dir.parent / "onenote" / "page_realistic.xml").read_text("utf-8")
    top = add_text_xml(xml, "Unu\n\nDoi <b>", "top")
    assert "{O2}" in top and "{O3}" not in top and "{O1}" not in top  # doar primul bloc, nu titlul
    page, _ = parse_page(top.replace("<one:Page ", '<one:Page name="x" '), "", [])
    assert [b.text for b in page.blocks][:2] == ["Unu", "Doi <b>"]  # textul rămâne text, nu HTML
    end = add_text_xml(xml, "Final", "end")
    assert "{O3}" in end and "{O2}" not in end
    with pytest.raises(ValueError):
        add_text_xml(xml, " \n ", "top")


def test_apply_rename_text_and_stale_then_restore(data):  # noqa: F811
    j = Journal(data)
    writer = writer_for(data)
    old_title = _where(writer)["sample-p027"][1]
    before_xml = writer.get_page_xml("sample-p027")
    ren = j.add("sample-p027", "rename", target="VPN – instalare (2026)")
    top = j.add("sample-p027", "add_text", target="top\tVerificat de echipă\nVezi și pagina nouă")
    end = j.add("sample-p027", "add_text", target="end\tUltimul rând")
    stale = j.add("sample-p027", "mark_stale")
    settings = Settings(write_enabled=True)
    items = plan(data, writer, settings)
    assert [i.action for i in items] == ["rename", "add_text", "add_text", "mark_stale"]
    assert items[-1].target == "[ÎNVECHIT] VPN – instalare (2026)"  # prefixul pe titlul nou
    assert items[1].reason == "at_top" and items[2].reason == "at_end"
    result = apply(data, writer, settings, [i.decision_id for i in items])
    assert len(result.done) == 4 and not result.errors

    assert _where(writer)["sample-p027"][1] == "[ÎNVECHIT] VPN – instalare (2026)"
    text = _text(writer, "sample-p027")
    assert text[:2] == ["Verificat de echipă", "Vezi și pagina nouă"]
    assert text[-1].endswith("Ultimul rând")
    assert object_ids(before_xml) <= object_ids(writer.get_page_xml("sample-p027"))  # nimic din pagină nu s-a pierdut
    assert plan(data, writer, settings) == []

    rows = {r["decision_id"]: r for r in Journal(data).applied()}
    assert len(rows[top.id]["added_ids"].split(",")) == 2
    for d in (stale, end, top, ren):  # restaurare în ordine inversă
        restore(data, writer, settings, rows[d.id]["id"])
    assert _where(writer)["sample-p027"][1] == old_title
    assert _text(writer, "sample-p027") == [b for b in _text_from(before_xml)]


def _text_from(xml):
    page, _ = parse_page(xml, "", [])
    return [b.text for b in page.blocks]


def test_later_decision_on_page_we_edited_is_not_changed(data):  # noqa: F811
    j = Journal(data)
    writer = writer_for(data)
    settings = Settings(write_enabled=True)
    ren = j.add("sample-p024", "rename", target="Altul")
    assert apply(data, writer, settings, [ren.id]).done
    arch = j.add("sample-p024", "archive")
    items = plan(data, writer, settings)
    assert [(i.decision_id, i.status) for i in items] == [(arch.id, "ready")]  # schimbarea e a noastră
    # o schimbare făcută de altcineva după aceea se vede iar
    _, _, page = writer._find("sample-p024")
    page["lastModifiedTime"] = "2099-01-01T00:00:00Z"
    writer.save()
    assert plan(data, writer, settings)[0].reason == "changed"


def test_same_title_is_skipped(data):  # noqa: F811
    writer = writer_for(data)
    d = Journal(data).add("sample-p005", "rename", target=_where(writer)["sample-p005"][1])
    item = plan(data, writer, Settings(write_enabled=True))[0]
    assert (item.decision_id, item.status, item.reason) == (d.id, "skip", "same_title")


def test_added_paragraph_ids_only_new_ones(fixture_dir):
    xml = (fixture_dir.parent / "onenote" / "page_realistic.xml").read_text("utf-8")
    after = add_text_xml(xml, "Nou", "end").replace("<one:OE><one:T>Nou", '<one:OE objectID="{N1}"><one:T>Nou')
    assert added_paragraph_ids(xml, after, "Nou") == ["{N1}"]
    assert title_of(xml)


def test_server_rename_and_add_text(server, data):  # noqa: F811
    r = _req(server, "POST", "/api/decision", {"ds": "demo", "page": "sample-p024", "action": "rename", "target": ""})
    assert r[0] == 400
    assert _req(server, "POST", "/api/decision", {"ds": "demo", "page": "sample-p024", "action": "rename",
                                                  "target": "Titlu <b>nou</b>"})[0] == 200
    assert _req(server, "POST", "/api/decision", {"ds": "demo", "page": "sample-p024", "action": "add_text",
                                                  "target": "end\tText"})[0] == 200
    plan_ = _req(server, "GET", "/api/plan?ds=demo")[1]
    assert [i["action"] for i in plan_["items"]] == ["rename", "add_text"]
    assert plan_["items"][0]["target"] == "Titlu <b>nou</b>"  # text, nu HTML
