from mutmut import mutate, count_mutations, ALL
import pytest


@pytest.mark.parametrize(
    'actual, expected', [
        ('1+1', '2-2'),
        ('1-1', '2+2'),
        ('1*1', '2/2'),
        ('1/1', '2*2'),
        # ('1.0', '1.0000000000000002'),  # using numpy features
        ('1.0', '101.0'),
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
        ("0x0", "1"),
        ("0b0", "1"),
        ("1<2", "2<=3"),
        ('(1, 2)', '(2, 3)'),
        ("1 in (1, 2)", "2 not in (2, 3)"),
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
        ('1.0e10', '1.0e11'),
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
    assert mutate(actual, ALL, context__dict_synonyms=['Struct', 'FooBarDict'])[0] == expected


def test_mutate_all():
    assert mutate('def foo():\n    return 1+1', ALL) == ('def foo():\n    return 2-2\n', 3)


def test_count_available_mutations():
    assert count_mutations('def foo():\n    return 1+1') == 3


def test_perform_one_indexed_mutation():
    assert mutate('1+1', mutate_index=0) == ('2+1', 1)
    assert mutate('1+1', mutate_index=1) == ('1+2', 1)
    assert mutate('1+1', mutate_index=2) == ('1-1', 1)

    # TODO: should this case raise an exception?
    assert mutate('def foo():\n    return 1', mutate_index=2) == ('def foo():\n    return 1\n', 0)


def test_function():
    assert mutate("def capitalize(s):\n    return s[0].upper() + s[1:] if s else s\n", mutate_index=0) == ("def capitalize(s):\n    return s[1].upper() + s[1:] if s else s\n", 1)
    assert mutate("def capitalize(s):\n    return s[0].upper() + s[1:] if s else s\n", mutate_index=1) == (
"def capitalize(s):\n    return s[0].upper() + s[2:] if s else s\n", 1)


def test_pragma_no_mutate():
    source = """def foo():\n    return 1+1  # pragma: no mutate\n"""
    assert mutate(source, ALL) == (source, 0)


def test_mutate_decorator():
    source = """@foo\ndef foo():\n    pass\n"""
    assert mutate(source, ALL) == (source.replace('@foo', ''), 1)


def test_mutate_dict():
    source = "dict(a=b, c=d)"
    assert mutate(source, 1) == ("dict(a=b, cXX=d)", 1)


def test_mutation_index():
    source = '''
    
a = b
b = c + a 
d = 4 - 1

    
    '''.strip()
    num_mutations = count_mutations(source=source)
    mutants = [mutate(source=source, mutate_index=i) for i in range(num_mutations)]
    assert len(mutants) == len(set(mutants))  # no two mutants should be the same

    # invalid mutation index should not mutate anything
    mutated_source, count = mutate(source=source, mutate_index=num_mutations + 1)
    assert mutated_source.strip() == source
    assert count == 0


# def test_mutate_files():
#     import os
#     for dirpath, dirnames, filenames in os.walk('/Users/andersh/triresolve/'):
#         for f in filenames:
#             if f.endswith('.py'):
#                 fullpath = os.path.join(dirpath, f)
#                 if fullpath in {
#                     '/Users/andersh/triresolve/.tox/py27/lib/python2.7/site-packages/Crypto/PublicKey/_slowmath.py',
#                     '/Users/andersh/triresolve/.tox/py27/lib/python2.7/site-packages/Crypto/SelfTest/Util/test_number.py',
#                     '/Users/andersh/triresolve/.tox/py27/lib/python2.7/site-packages/ecdsa/ecdsa.py',
#                     '/Users/andersh/triresolve/.tox/py27/lib/python2.7/site-packages/ecdsa/numbertheory.py',
#                     '/Users/andersh/triresolve/.tox/py27/lib/python2.7/site-packages/numpy/core/tests/test_umath.py',
#                 }:
#                     continue
#                 if 'py3' in fullpath:
#                     continue
#                 # print fullpath
#                 full_source = open(fullpath).read()
#                 if 'yield from' in full_source:
#                     continue
#                 mutate(full_source, ALL)
