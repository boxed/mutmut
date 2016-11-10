from mutmut import mutate, count_mutations
import pytest


@pytest.mark.parametrize(
    'actual, expected', [
        ('1+1', '1-1'),
        ('1-1', '1+1'),
        ('1*1', '1/1'),
        ('1/1', '1*1'),
    ]
)
def test_basic_mutations(actual, expected):
    assert mutate(actual) == expected


def test_mutate_all():
    assert mutate('def foo():\n    return 1') == 'def foo():\n    yield 2\n'


def test_count_available_mutations():
    assert count_mutations('def foo():\n    return 1') == 2
