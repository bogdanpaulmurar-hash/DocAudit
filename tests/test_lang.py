"""Documentație amestecată RO / EN / DE și locul datelor."""

from pathlib import Path

import pytest

from docaudit.__main__ import data_dir, main, resolve_folder
from docaudit.group.text import clean_title
from docaudit.i18n import t
from docaudit.lang import detect_language, stale_markers_in
from docaudit.sample import build_sample


@pytest.mark.parametrize("text,lang", [
    ("Deschide aplicația și completează perioada pentru concediu de odihnă", "ro"),
    ("Open the app and fill in the period for your annual leave", "en"),
    ("Öffne die HR-App und trage den Zeitraum für den Urlaub ein", "de"),
    ("VPN 443", None),
])
def test_detect_language(text, lang):
    assert detect_language(text) == lang


def test_stale_markers_all_languages():
    assert stale_markers_in("Notă: varianta veche, nu mai folosiți după 2021.") == ["nu mai folositi", "varianta veche"]
    assert stale_markers_in("This page is DEPRECATED, do not use.") == ["deprecated", "do not use"]
    assert stale_markers_in("Diese Anleitung ist veraltet und nicht mehr gültig.") == ["veraltet", "nicht mehr gultig"]
    assert stale_markers_in("Procedura curentă, verificată azi.") == []


def test_german_title_noise():
    assert clean_title("Anleitung: Urlaubsantrag stellen (aktualisiert)") == "urlaubsantrag stellen"
    assert clean_title("Kopie - Urlaubsantrag stellen, Schritt für Schritt") == "urlaubsantrag stellen"


def test_sample_has_three_languages():
    _, pages, _, exp = build_sample()
    langs = {detect_language(p.text) for p in pages}
    assert {"ro", "en", "de"} <= langs
    de_pages = [p for p in pages if detect_language(p.text) == "de"]
    translations = {b for _, b in exp["translations"]}
    assert any(p.id in translations for p in de_pages)  # o traducere DE
    assert any(p.id in exp["ungrouped"] for p in de_pages)  # și pagini DE unice


def test_german_messages(monkeypatch):
    monkeypatch.setenv("DOCAUDIT_LANG", "de")
    assert t("cli.validate.ok", pages=2, schema=1) == "Format gültig: 2 Seiten, Schema v1"


def test_data_dir_is_local_not_repo(monkeypatch, tmp_path):
    monkeypatch.delenv("DOCAUDIT_DATA", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert data_dir() == tmp_path / "DocAudit" / "data"
    monkeypatch.delenv("LOCALAPPDATA")
    assert data_dir() == Path.home() / ".local" / "share" / "docaudit"
    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path / "x"))
    assert data_dir() == tmp_path / "x"


def test_resolve_folder_by_name(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path))
    assert resolve_folder(Path("demo")) == tmp_path / "demo"
    assert resolve_folder(tmp_path / "alt") == tmp_path / "alt"
    assert resolve_folder(Path("a") / "b") == Path("a") / "b"


def test_extract_out_by_name_goes_to_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCAUDIT_DATA", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert main(["extract", "--demo", "--out", "test"]) == 0
    assert (tmp_path / "test" / "pages.jsonl").is_file()
    assert main(["group", "test"]) == 0
    assert (tmp_path / "test" / "groups.json").is_file()


def test_download_model_without_library(monkeypatch):
    import builtins

    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("sentence_transformers"):
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    assert main(["download-model"]) == 2


def test_output_on_cp1252_console(monkeypatch, tmp_path):
    """Install.bat rulează `make-icon … >nul`: pe Windows ieșirea e cp1252 și nu știe „ț” din „Iconiță”."""
    import io
    import sys

    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    monkeypatch.setenv("DOCAUDIT_LANG", "ro")
    assert main(["make-icon", str(tmp_path / "i")]) == 0
    sys.stdout.flush()
    assert "Iconiță".encode("utf-8") in raw.getvalue()
