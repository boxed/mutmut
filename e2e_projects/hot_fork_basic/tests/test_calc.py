"""Tests for calc module."""

from calc import divide


def test_divide():
    assert divide(10, 2) == 5


def test_divide_by_zero():
    assert divide(10, 0) == 0
