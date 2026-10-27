import json
from importlib import resources

from docaudit.i18n import LANGUAGES, t


def test_same_keys_in_all_languages():
    keys = [set(json.loads(resources.files("docaudit").joinpath(f"locales/{l}.json").read_text("utf-8")))
            for l in LANGUAGES]
    assert all(k == keys[0] for k in keys)


def test_lang_switch(monkeypatch):
    monkeypatch.setenv("DOCAUDIT_LANG", "en")
    assert t("cli.validate.ok", pages=3, schema=1) == "Valid format: 3 pages, schema v1"
    monkeypatch.setenv("DOCAUDIT_LANG", "xx")
    assert t("cli.validate.ok", pages=3, schema=1).startswith("Format valid")


def test_missing_key_falls_back_to_key():
    assert t("nu.exista") == "nu.exista"
