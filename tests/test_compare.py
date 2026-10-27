"""Etapa 5: compararea paginilor din același grup."""

import hashlib
import json
import shutil
import time

import pytest

from docaudit.__main__ import main
from docaudit.compare.analyze import compare_group
from docaudit.compare.evaluate import evaluate_compare
from docaudit.compare.run import FINDINGS_FILE, load_findings, run_compare
from docaudit.compare.steps import is_value, masked, out_of_order, step_similarity, values_of
from docaudit.group.run import run_grouping
from docaudit.model import Block, Page
from docaudit.safety import no_network


@pytest.fixture
def grouped(tmp_path, fixture_dir):
    shutil.copytree(fixture_dir, tmp_path / "d")
    run_grouping(tmp_path / "d")
    return tmp_path / "d"


def _page(pid, steps, modified="2025-06-01T10:00:00Z", text_extra="", title="Procedură"):
    blocks = [Block("list_item", s, level=1) for s in steps]
    text = "\n".join([f"{i + 1}. {s}" for i, s in enumerate(steps)] + ([text_extra] if text_extra else []))
    return Page(id=pid, notebook="NB", section_path=["S"], title=title, created=modified,
                modified=modified, text=text, blocks=blocks)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_values_and_masking():
    assert values_of("Setează portul 443 și protocolul TLS.") == ("443", "TLS")
    assert values_of(r"Introdu calea \\print01.example.test\Etaj2.") == (r"\\print01.example.test\Etaj2",)
    assert values_of("Adaugă utilizatorul în grupul GRP-Users.") == ("GRP-Users",)
    assert not is_value("Autentifică-te") and not is_value("e-mail")
    assert masked("Setează portul 443") == ["seteaza", "portul", "<v>"]
    # același pas reformulat, cu altă valoare
    assert step_similarity("Setează portul 443 și protocolul TLS.", "Configurează portul 8443 și protocolul TLS.") > 0.7
    assert step_similarity("Setează portul 443.", "Tipărește o pagină de test.") < 0.5
    assert out_of_order([0, 2, 1, 3, 4]) in ([1], [2])
    assert out_of_order([0, 1, 2]) == []


def test_sample_meets_targets(grouped):
    exp = json.loads((grouped / "expected.json").read_text("utf-8"))
    before = {name: _sha(grouped / name) for name in ("pages.jsonl", "manifest.json", "groups.json")}
    start = time.perf_counter()
    with no_network():
        run_compare(grouped)
    assert time.perf_counter() - start < exp["targets"]["max_seconds_cpu_without_embeddings"]
    # comparația nu atinge datele extrase și nici grupurile
    assert before == {name: _sha(grouped / name) for name in before}

    s = evaluate_compare(load_findings(grouped), exp)
    assert s.conflict_recall >= exp["targets"]["conflict_recall_min"], s.missed
    assert s.false_alarm_rate <= exp["targets"]["conflict_false_alarm_max"]
    assert s.stale_found >= exp["targets"]["stale_found_min"], s.missed
    assert s.step_diffs_found == s.step_diffs_planted, s.missed
    assert s.duplicates_found == s.duplicates_planted


def test_findings_have_evidence(grouped):
    data = run_compare(grouped)
    conflict = next(f for f in data.findings() if f.kind == "value_conflict" and "sample-p039" in f.details["differing"])
    assert conflict.details["values"]["sample-p039"] == "8443"
    assert conflict.details["values"]["sample-p005"] == "443"
    assert "8443" in conflict.details["texts"]["sample-p039"]
    stale = {f.pages[0]: f for f in data.findings() if f.kind == "stale"}
    assert any(r["reason"] == "lower_version" for r in stale["sample-p024"].details["reasons"])
    # pagina sugerată ca referință nu e una învechită
    for g in data.groups:
        assert g.reference not in stale
    shared = {tuple(f.pages) for f in data.shared_images}
    assert ("sample-p017", "sample-p057") in shared


def test_missing_and_reordered_steps():
    base = ["Deschide portalul.", "Alege nivelul -1.", "Atașează talonul.", "Ridică cardul.", "Semnează."]
    pages = [
        _page("a", base),
        _page("b", [base[0], base[2], base[1], base[3], base[4]]),
        _page("c", base[:3] + base[4:]),
    ]
    rep = compare_group("g", pages)
    kinds = {(f.kind, tuple(f.pages)) for f in rep.findings}
    assert ("missing_step", ("c",)) in kinds
    assert any(k == "reordered" and p == ("b",) for k, p in kinds)
    assert not any(f.kind == "value_conflict" for f in rep.findings)


def test_two_pages_reordered_names_both():
    steps = ["Deschide aplicația.", "Alege folderul.", "Pornește arhivarea.", "Verifică."]
    rep = compare_group("g", [_page("a", steps), _page("b", [steps[0], steps[2], steps[1], steps[3]])])
    reordered = [f for f in rep.findings if f.kind == "reordered"]
    assert len(reordered) == 1 and reordered[0].pages == ["a", "b"]


def test_stale_markers_in_three_languages():
    steps = ["Open the portal portal.example.test.", "Set the port to 443.", "Restart the service."]
    for marker in ("Notă: nu mai folosiți această pagină.", "Deprecated, do not use.", "Veraltet, nicht mehr verwenden."):
        rep = compare_group("g", [_page("a", steps), _page("b", steps, text_extra=marker)])
        assert [f.pages for f in rep.findings if f.kind == "stale"] == [["b"]]
        assert rep.reference == "a"


def test_other_language_pages_are_not_compared_step_by_step():
    ro = ["Deschide aplicația HR la hr.example.test.", "Completează perioada cu 5 zile înainte.",
          "Trimite cererea către manager și așteaptă aprobarea."]
    de = ["Öffne die HR-App unter hr.example.test.", "Trage den Zeitraum mindestens 5 Arbeitstage im Voraus ein.",
          "Sende den Antrag an die Führungskraft und warte auf die Genehmigung."]
    rep = compare_group("g", [_page("ro1", ro), _page("ro2", ro), _page("de1", de)])
    assert rep.other_language == ["de1"]
    assert not [f for f in rep.findings if f.kind in ("missing_step", "extra_step")]


def test_no_false_conflict_for_reworded_steps():
    a = ["Descarcă clientul versiunea 5.2.", "Setează portul 443.", "Verifică pictograma."]
    b = ["Ia clientul versiunea 5.2.", "Configurează portul 443.", "Controlează pictograma."]
    rep = compare_group("g", [_page("a", a), _page("b", b)])
    assert not rep.findings


def test_cli_compare(grouped, capsys, monkeypatch):
    monkeypatch.setenv("DOCAUDIT_LANG", "ro")
    assert main(["compare", str(grouped)]) == 0
    out = capsys.readouterr().out
    assert "8443" in out and "Nimic nu s-a modificat" in out
    assert (grouped / FINDINGS_FILE).is_file()
    assert main(["compare-eval", str(grouped)]) == 0
    assert "20/20" in capsys.readouterr().out


def test_cli_compare_without_groups(tmp_path, fixture_dir, capsys):
    shutil.copytree(fixture_dir, tmp_path / "d")
    assert main(["compare", str(tmp_path / "d")]) == 1
    assert "group" in capsys.readouterr().out
