from pathlib import Path

import pytest


@pytest.fixture
def testdata():
    return Path(__file__).parent / "testdata"
