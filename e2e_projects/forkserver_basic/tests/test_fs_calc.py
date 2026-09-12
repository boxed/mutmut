from fs_calc import add
from fs_calc import mul
from fs_calc import sub


def test_add():
    assert add(1, 2) == 3


def test_sub():
    assert sub(5, 2) == 3


def test_mul():
    assert mul(3, 4) == 12
