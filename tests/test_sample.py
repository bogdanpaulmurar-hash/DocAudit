"""Eșantionul fictiv: mărime, cazuri plantate, determinism, fără date reale."""

import json
import re
from itertools import combinations

from docaudit.model import read_pages, validate_dataset
from docaudit.safety import tree_digest
from docaudit.sample import build_sample, write_sample


def test_fixture_is_valid(fixture_dir):
    assert validate_dataset(fixture_dir) == []


def test_fixture_matches_generator(tmp_path, fixture_dir):
    """Fixture-ul din repo e exact ce produce generatorul (determinism)."""
    write_sample(tmp_path)
    assert tree_digest(tmp_path) == tree_digest(fixture_dir)


def test_size_and_planted_cases():
    _, pages, images, exp = build_sample()
    assert 50 <= len(pages) <= 100 and len(pages) == 80
    assert len(exp["groups"]) == 15
    assert len({c["group"] for c in exp["conflicts"] if c["group"]}) >= 12
    assert len({s["group"] for s in exp["step_diffs"]}) == 6
    assert len(exp["stale"]) == 10
    assert len(exp["duplicates"]) == 5
    assert len(exp["translations"]) == 3
    assert len(exp["ungrouped"]) == 25
    assert sum(len(v) for v in exp["image_duplicates"].values()) == 6
    assert len(images) == 5


def test_every_page_has_exactly_one_role():
    _, pages, _, exp = build_sample()
    grouped = [p for g in exp["groups"] for p in g["pages"] + g["translation_pages"]]
    all_ids = grouped + exp["ungrouped"]
    assert sorted(all_ids) == sorted(p.id for p in pages)
    assert len(all_ids) == len(set(all_ids))


def test_conflicts_are_visible_in_text():
    _, pages, _, exp = build_sample()
    text = {p.id: p.text for p in pages}
    for c in exp["conflicts"]:
        for pid, value in c["values"].items():
            assert value in text[pid], (c["slot"], pid)


def test_stale_pages_are_older_than_their_group():
    _, pages, _, exp = build_sample()
    modified = {p.id: p.modified for p in pages}
    for g in exp["groups"]:
        stale = [p for p in g["pages"] if p in exp["stale"]]
        fresh = [p for p in g["pages"] if p not in exp["stale"]]
        for s in stale:
            assert all(modified[s] < modified[f] for f in fresh)


def test_pages_spread_over_notebooks():
    manifest, pages, _, _ = build_sample()
    assert len(manifest.notebooks) == 3
    assert len({p.notebook for p in pages}) == 3


def test_ids_do_not_leak_answers(fixture_dir):
    """Titlurile pot diferi, dar id-urile și sursa nu dau indicii despre grup."""
    for p in read_pages(fixture_dir):
        assert re.fullmatch(r"sample-p\d{3}", p.id)
        assert p.source.ref == f"sample:{p.id}"


def test_no_real_data(fixture_dir):
    """Doar domenii și e-mailuri example.test; niciun domeniu public uzual."""
    raw = (fixture_dir / "pages.jsonl").read_text("utf-8")
    assert not re.search(r"\.(com|ro|net|org|io|eu|de|local|corp)\b", raw)
    for domain in re.findall(r"[\w.-]+@([\w.-]+)", raw):
        assert domain.rstrip(".").endswith("example.test")


def test_different_seed_changes_order_not_cases():
    _, a, _, ea = build_sample(seed=1)
    _, b, _, eb = build_sample(seed=2)
    assert [p.title for p in a] != [p.title for p in b]
    assert len(ea["stale"]) == len(eb["stale"]) == 10


def test_expected_pairs_are_inside_groups():
    _, _, _, exp = build_sample()
    members = {g["key"]: set(g["pages"]) for g in exp["groups"]}
    for a, b in exp["duplicates"]:
        assert any({a, b} <= m for m in members.values())
    pair_count = sum(len(list(combinations(m, 2))) for m in members.values())
    assert pair_count > 50  # destule perechi pentru un F1 cu sens
