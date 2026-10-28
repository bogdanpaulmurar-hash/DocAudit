from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_v1"


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE


@pytest.fixture(autouse=True)
def _no_shared_log(monkeypatch):
    """Testele nu copiază logul în folderul clonei."""
    monkeypatch.setenv("DOCAUDIT_LOG_SHARE", "0")
