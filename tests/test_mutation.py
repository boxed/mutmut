from mutmut import mutate, count_mutations
import pytest


@pytest.mark.parametrize(
    'actual, expected', [
        ('1+1', '2-2'),
        ('1-1', '2+2'),
        ('1*1', '2/2'),
        ('1/1', '2*2'),
        ('1.0', '1.0000000000000002'),
        ('True', 'False'),
        ('False', 'True'),
        ('"foo"', '"XXfooXX"'),
        ("'foo'", "'XXfooXX'"),
        ("u'foo'", "u'XXfooXX'"),
        ("0", "1"),
        ("1L", "2L"),
        # ("0L", "1L"),
        # ("0o0", "0o1"),
        ("0", "1"),
        ("0x0", "0x1"),
        ("0b0", "0b1"),
        ("1<2", "2<=3"),
        ('(1, 2)', '(2, 3)'),
        ("1 in (1, 2)", "2 not in (2, 3)"),
        ("1 not in (1, 2)", "2  in (2, 3)"),  # two spaces here because "not in" is two words
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
