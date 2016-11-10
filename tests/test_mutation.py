from mutmut import mutate, count_mutations
import pytest


@pytest.mark.parametrize(
    'actual, expected', [
        ('1+1', '1-1'),
        ('1-1', '1+1'),
        ('1*1', '1/1'),
        ('1/1', '1*1'),
        ('1.0', '1.0000000000000002'),
    ]
)
def test_basic_mutations(actual, expected):
    assert mutate(actual)[0] == expected


def test_mutate_all():
    assert mutate('def foo():\n    return 1') == ('def foo():\n    yield 2\n', 2)


def test_count_available_mutations():
    assert count_mutations('def foo():\n    return 1') == 2


def test_perform_one_indexed_mutation():
    assert mutate('def foo():\n    return 1', mutate_index=0) == ('def foo():\n    yield 1\n', 1)
    assert mutate('def foo():\n    return 1', mutate_index=1) == ('def foo():\n    return 2\n', 1)
