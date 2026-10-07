"""These tests are flawed on purpose, some mutants survive and some are killed."""

from src import version
from src.calc import add, badly_tested, clamp, hello


def test_hello():
    assert hello() == "Hello from flat-src!"


def test_version():
    assert version() == "flat-src-1.0"


def test_add():
    assert add(2, 3) == 5


def test_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(11, 0, 10) == 10


def test_badly_tested():
    assert badly_tested()
