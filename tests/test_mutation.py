from mutmut import mutate, count_mutations, ALL, Context, list_mutations
import pytest

from mutmut.__main__ import parse_mutation_id_str, get_mutation_id_str


@pytest.mark.parametrize(
    'actual, expected', [
        ("1 in (1, 2)", "2 not in (2, 3)"),
        ('1+1', '2-2'),
        ('1', '2'),
        ('1-1', '2+2'),
        ('1*1', '2/2'),
        ('1/1', '2*2'),
        # ('1.0', '1.0000000000000002'),  # using numpy features
        ('1.0', '2.0'),
        ('True', 'False'),
        ('False', 'True'),
        ('"foo"', '"XXfooXX"'),
        ("'foo'", "'XXfooXX'"),
        ("u'foo'", "u'XXfooXX'"),
        ("0", "1"),
        # ("1L", "2L"),
        # ("0L", "1L"),
        # ("0o0", "0o1"),
        ("0", "1"),
        ("0x0", "1"),
        ("0b0", "1"),
        ("1<2", "2<=3"),
        ('(1, 2)', '(2, 3)'),
        ("1 not in (1, 2)", "2  in (2, 3)"),  # two spaces here because "not in" is two words
        ("None is None", "None is not None"),
        ("None is not None", "None is None"),
        ("x if a else b", "x if a else b"),
        ('a or b', 'a and b'),
        ('a = b', 'a = None'),
        ('s[0]', 's[1]'),
        ('s[0] = a', 's[1] = None'),
        ('s[1:]', 's[2:]'),
        ('1j', '2j'),
        ('1.0j', '2.0j'),
        ('0o1', '2'),
        ('010', '9'),
        ('1.0e10', '10000000001.0'),
        ("'''foo'''", "'''foo'''"),  # don't mutate things we assume to be docstrings
        ("dict(a=b)", "dict(aXX=b)"),
        ("Struct(a=b)", "Struct(aXX=b)"),
        ("FooBarDict(a=b)", "FooBarDict(aXX=b)"),
        ("NotADictSynonym(a=b)", "NotADictSynonym(a=b)"),  # shouldn't be mutated
        ('from foo import *', 'from foo import *'),
        ('lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(show=False)))', 'lambda **kwargs: None'),
        ('lambda **kwargs: None', 'lambda **kwargs: 0'),
        ('a = {x for x in y}', 'a = None'),
        ('a = None', 'a = 7')
    ]
)
def test_basic_mutations(actual, expected):
    assert mutate(Context(source=actual, mutate_id=ALL, dict_synonyms=['Struct', 'FooBarDict']))[0] == expected


def test_mutate_all():
    assert mutate(Context(source='def foo():\n    return 1+1', mutate_id=ALL)) == ('def foo():\n    return 2-2\n', 3)


def test_mutate_both():
    source = 'a = b + c'
    mutations = list_mutations(Context(source=source))
    assert len(mutations) == 2
    assert mutate(Context(source=source, mutate_id=mutations[0])) == ('a = b - c', 1)
    assert mutate(Context(source=source, mutate_id=mutations[1])) == ('a = None', 1)


def test_count_available_mutations():
    assert count_mutations(Context(source='def foo():\n    return 1+1')) == 3


def test_perform_one_indexed_mutation():
    assert mutate(Context(source='1+1', mutate_id=('1+1', 0))) == ('2+1', 1)
    assert mutate(Context(source='1+1', mutate_id=('1+1', 1))) == ('1+2', 1)
    assert mutate(Context(source='1+1', mutate_id=('1+1', 2))) == ('1-1', 1)

    # TODO: should this case raise an exception?
    # assert mutate(Context(source='def foo():\n    return 1', mutate_id=2)) == ('def foo():\n    return 1\n', 0)


def test_function():
    source = "def capitalize(s):\n    return s[0].upper() + s[1:] if s else s\n"
    assert mutate(Context(source=source, mutate_id=(source.split('\n')[1], 0))) == ("def capitalize(s):\n    return s[1].upper() + s[1:] if s else s\n", 1)
    assert mutate(Context(source=source, mutate_id=(source.split('\n')[1], 1))) == ("def capitalize(s):\n    return s[0].upper() + s[2:] if s else s\n", 1)


def test_pragma_no_mutate():
    source = """def foo():\n    return 1+1  # pragma: no mutate\n"""
    assert mutate(Context(source=source, mutate_id=ALL)) == (source, 0)


def test_pragma_no_mutate_and_no_cover():
    source = """def foo():\n    return 1+1  # pragma: no cover, no mutate\n"""
    assert mutate(Context(source=source, mutate_id=ALL)) == (source, 0)


def test_mutate_decorator():
    source = """@foo\ndef foo():\n    pass\n"""
    assert mutate(Context(source=source, mutate_id=ALL)) == (source.replace('@foo', ''), 1)


def test_mutate_dict():
    source = "dict(a=b, c=d)"
    assert mutate(Context(source=source, mutate_id=(source, 1))) == ("dict(a=b, cXX=d)", 1)


def test_performed_mutation_ids():
    source = "dict(a=b, c=d)"
    context = Context(source=source)
    mutate(context)
    # we found two mutation points: mutate "a" and "c"
    assert context.performed_mutation_ids == [(source, 0), (source, 1)]


def test_mutation_id_str_roundtrip():
    mutation_id = ('    foo = "bar"', 7)
    assert mutation_id == parse_mutation_id_str(get_mutation_id_str(mutation_id))

# TODO: this test becomes incorrect with the new mutation_id system, should try to salvage the idea though...
# def test_mutation_index():
#     source = '''
#
# a = b
# b = c + a
# d = 4 - 1
#
#
#     '''.strip()
#     num_mutations = count_mutations(Context(source=source))
#     mutants = [mutate(Context(source=source, mutate_id=i)) for i in range(num_mutations)]
#     assert len(mutants) == len(set(mutants))  # no two mutants should be the same
#
#     # invalid mutation index should not mutate anything
#     mutated_source, count = mutate(Context(source=source, mutate_id=num_mutations + 1))
#     assert mutated_source.strip() == source
#     assert count == 0
