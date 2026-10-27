from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_v1"


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE
