"""Etapa 4: gruparea paginilor după asemănare."""

import copy
import json
import shutil
import time

import pytest

from docaudit.__main__ import main
from docaudit.group.cluster import cluster
from docaudit.group.evaluate import evaluate
from docaudit.group.overrides import GroupOverrides
from docaudit.group.run import load_groups, run_grouping, scan_thresholds
from docaudit.group.semantic import SemanticUnavailable, semantic_scores
from docaudit.group.similarity import PairScore, SimilaritySettings, score_pairs
from docaudit.group.text import clean_title, normalize
from docaudit.safety import no_network
from docaudit.sample import build_sample


@pytest.fixture
def data(tmp_path, fixture_dir):
    shutil.copytree(fixture_dir, tmp_path / "d")
    return tmp_path / "d"


def _expected(folder):
    return json.loads((folder / "expected.json").read_text("utf-8"))


def test_normalize_and_titles():
    assert normalize("Ghid: Rețea  VPN-ul (Nou)!") == "ghid retea vpn ul nou"
    assert clean_title("Ghid: instalare client VPN (actualizat)") == "instalare client vpn"
    assert clean_title("Instalare client VPN, pe pași") == "instalare client vpn"


def test_sample_meets_target(data):
    exp = _expected(data)
    with no_network():
        result = run_grouping(data)
    score = evaluate([g.pages for g in result.groups], exp)
    assert score.f1 >= exp["targets"]["grouping_pairwise_f1_min"]
    grouped = {p for g in result.groups for p in g.pages}
    assert not grouped & set(exp["distractors"])  # paginile-capcană rămân singure
    translations = {p for g in exp["groups"] for p in g["translation_pages"]}
    assert not grouped & translations  # fără sens (embeddings), traducerile nu se pot lega


def test_grouping_writes_only_groups_file(data):
    before = {p.name: p.read_bytes() for p in data.iterdir() if p.is_file()}
    run_grouping(data)
    after = {p.name: p.read_bytes() for p in data.iterdir() if p.is_file()}
    assert set(after) - set(before) == {"groups.json"}
    assert all(after[k] == v for k, v in before.items())
    saved = load_groups(data)
    assert saved["threshold"] == 0.6 and len(saved["groups"]) == 15


def test_scan_thresholds(data):
    rows = scan_thresholds(data, [0.3, 0.6, 0.99])
    assert rows[0][2] >= rows[1][2] >= rows[2][2]  # prag mai mare = mai puține pagini grupate


def _pairs(*items):
    return sorted((PairScore(a, b, s, s, s) for a, b, s in items), key=lambda p: -p.score)


def test_cluster_threshold_and_cannot_link_blocks_chaining():
    pairs = _pairs(("a", "b", 0.9), ("b", "c", 0.8), ("c", "d", 0.5))
    groups, alone = cluster(list("abcd"), pairs, 0.6)
    assert [g.pages for g in groups] == [["a", "b", "c"]] and alone == ["d"]
    groups, _ = cluster(list("abcd"), pairs, 0.6, cannot_link=[["a", "c"]])
    assert [g.pages for g in groups] == [["a", "b"]]  # c nu se mai poate lega prin b


def test_cluster_must_link_and_labels():
    groups, _ = cluster(list("abc"), _pairs(("a", "b", 0.9)), 0.6, must_link=[["b", "c"]],
                        titles={"a": "A", "b": "B", "c": "C"})
    assert groups[0].pages == ["a", "b", "c"] and groups[0].label == "B"
    assert groups[0].min_link == 0.9


def test_overrides_detach_and_merge(data):
    exp = _expected(data)
    vpn = next(g for g in exp["groups"] if g["key"] == "vpn")["pages"]
    run_grouping(data)
    ov = GroupOverrides.load(data)
    ov.detach(vpn[0], vpn)
    ov.save(data)
    result = run_grouping(data)
    assert vpn[0] in result.ungrouped
    # o pagină fără legătură, unită de mână
    lone = exp["ungrouped"][0]
    ov = GroupOverrides.load(data)
    ov.merge(vpn[0], lone)
    ov.save(data)
    result = run_grouping(data)
    assert any({vpn[0], lone} <= set(g.pages) for g in result.groups)
    ov = GroupOverrides.load(data)
    assert ov.must_link == [sorted([vpn[0], lone])]
    ov.detach(lone, [vpn[0], lone])
    assert ov.must_link == []


def test_semantic_scores_can_join_translations():
    _, pages, _, exp = build_sample()
    index = {p.id: i for i, p in enumerate(pages)}
    sem = {}
    for ro, en in exp["translations"]:
        i, j = sorted((index[ro], index[en]))
        sem[(i, j)] = 0.95
    pairs = score_pairs(pages, SimilaritySettings(), sem)
    groups, _ = cluster([p.id for p in pages], pairs, 0.6)
    score = evaluate([g.pages for g in groups], exp, with_translations=True)
    assert score.recall > 0.9 and score.precision == 1.0


def test_semantic_low_similarity_never_lowers_score():
    _, pages, _, _ = build_sample()
    base = {(p.a, p.b): p.score for p in score_pairs(pages)}
    with_sem = {(p.a, p.b): p.score for p in score_pairs(pages, semantic={(0, 1): 0.1})}
    assert all(with_sem[k] == v for k, v in base.items())


def test_semantic_unavailable_without_model():
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        with pytest.raises(SemanticUnavailable):
            semantic_scores([])
    else:
        pytest.skip("sentence-transformers instalat")


def test_speed_on_larger_set():
    _, pages, _, _ = build_sample()
    big = []
    for k in range(5):
        for p in pages:
            q = copy.deepcopy(p)
            q.id = f"{p.id}-{k}"
            big.append(q)
    start = time.perf_counter()
    score_pairs(big)
    assert time.perf_counter() - start < 15  # 400 de pagini, cu multe copii


def test_cli_group_flow(data, capsys):
    assert main(["group", str(data), "--scan"]) == 0
    assert main(["group", str(data)]) == 0
    assert main(["group-eval", str(data)]) == 0
    assert "F1 1.00" in capsys.readouterr().out
    page = load_groups(data)["groups"][0]["pages"][0]
    assert main(["group-detach", str(data), page]) == 0
    assert main(["group-detach", str(data), "nu-exista"]) == 1
    assert main(["group-merge", str(data), page, "sample-p001"]) == 0
    assert GroupOverrides.load(data).must_link


def test_cli_semantic_missing(data, monkeypatch):
    import builtins

    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("sentence_transformers"):
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    assert main(["group", str(data), "--semantic"]) == 2
