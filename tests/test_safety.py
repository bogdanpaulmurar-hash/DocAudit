"""Garanțiile „doar local” și „fără scriere în sursă”."""

import socket
import urllib.request

import pytest

from docaudit.__main__ import main
from docaudit.model import read_pages, validate_dataset
from docaudit.safety import NetworkBlockedError, is_loopback, no_network, tree_digest


def test_network_is_blocked_inside_guard():
    with no_network():
        with pytest.raises(NetworkBlockedError):
            socket.create_connection(("example.test", 443), timeout=1)
        with pytest.raises(NetworkBlockedError):
            urllib.request.urlopen("http://example.test", timeout=1)
    # după ieșire, funcțiile originale sunt la loc
    assert socket.create_connection.__name__ == "create_connection"


def test_reading_and_validating_do_not_touch_network_or_files(fixture_dir):
    before = tree_digest(fixture_dir)
    with no_network():
        assert validate_dataset(fixture_dir) == []
        assert len(read_pages(fixture_dir)) == 80
        assert main(["validate", str(fixture_dir)]) == 0
    assert tree_digest(fixture_dir) == before


def test_sample_generation_is_offline(tmp_path):
    with no_network():
        assert main(["sample", "--out", str(tmp_path)]) == 0


def test_tree_digest_detects_changes(tmp_path):
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    d1 = tree_digest(tmp_path)
    (tmp_path / "a.txt").write_text("2", encoding="utf-8")
    assert tree_digest(tmp_path) != d1


@pytest.mark.parametrize("host,ok", [
    ("127.0.0.1", True), ("::1", True), ("localhost", True),
    ("0.0.0.0", False), ("192.168.1.10", False), ("example.test", False),
])
def test_loopback_only(host, ok):
    assert is_loopback(host) is ok
