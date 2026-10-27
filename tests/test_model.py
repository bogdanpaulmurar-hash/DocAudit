"""Formatul normalizat v1: scriere, citire, validare."""

import json

from docaudit.model import (
    Block,
    ImageRef,
    Manifest,
    Page,
    Source,
    read_manifest,
    read_pages,
    validate_dataset,
    validate_page_dict,
    write_dataset,
)


def _page(**kw) -> Page:
    base = dict(
        id="p1", notebook="Caiet", section_path=["Secțiune"], title="Titlu",
        created="2025-01-01T10:00:00Z", modified="2025-02-01T10:00:00Z", text="Text",
        blocks=[Block("para", "Text")], source=Source(kind="sample"),
    )
    base.update(kw)
    return Page(**base)


def _manifest(n: int) -> Manifest:
    return Manifest(source=Source(kind="sample"), extracted_at="2026-01-01T00:00:00Z",
                    notebooks=[{"name": "Caiet", "sections": ["Secțiune"]}],
                    selection={"notebooks": ["Caiet"], "sections": [], "pages": []}, page_count=n)


def test_roundtrip(tmp_path):
    pages = [_page(), _page(id="p2", title="Ăîșț diacritice")]
    write_dataset(tmp_path, _manifest(2), pages)
    assert read_pages(tmp_path) == pages
    assert read_manifest(tmp_path).page_count == 2
    assert validate_dataset(tmp_path) == []


def test_valid_page_has_no_errors():
    assert validate_page_dict(_page().to_dict()) == []


def test_detects_bad_fields():
    d = _page().to_dict()
    d["schema_version"] = 2
    d["section_path"] = []
    d["modified"] = "ieri"
    d["blocks"] = [{"type": "video", "text": "", "level": 0}]
    d["images"] = [{"sha256": "abc"}]
    d["source"] = {"kind": "altceva", "ref": ""}
    errors = " | ".join(validate_page_dict(d))
    for fragment in ("schema_version", "section_path", "modified", "tip necunoscut", "sha256", "sursă"):
        assert fragment in errors


def test_modified_before_created():
    d = _page(created="2025-03-01T00:00:00Z", modified="2025-01-01T00:00:00Z").to_dict()
    assert any("înainte" in e for e in validate_page_dict(d))


def test_dataset_errors(tmp_path):
    sha = "0" * 64
    write_dataset(tmp_path, _manifest(5), [_page(), _page(), _page(id="p3", images=[ImageRef(sha256=sha)])])
    with (tmp_path / "pages.jsonl").open("a", encoding="utf-8") as f:
        f.write("{nu e json\n")
    errors = " | ".join(validate_dataset(tmp_path))
    assert "id duplicat" in errors
    assert "lipsește din images/" in errors
    assert "JSON invalid" in errors
    assert "page_count 5" in errors


def test_missing_files(tmp_path):
    assert validate_dataset(tmp_path) == ["lipsește manifest.json"]
    (tmp_path / "manifest.json").write_text(json.dumps({}), encoding="utf-8")
    assert validate_dataset(tmp_path) == ["lipsește pages.jsonl"]
