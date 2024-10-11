from parso import parse

from mutmut3 import (
    trampoline_impl,
    yield_mutants_for_module,
)


def test_yield_mutants_for_module():
    source = """
a + 1

def foo(a, b, c):
    return a + b * c
"""

    expected = trampoline_impl + """

a + 1

def foo__mutmut_orig(a, b, c):
    return a + b * c

def foo__mutmut_1(a, b, c):
    return a - b * c

def foo__mutmut_2(a, b, c):
    return a + b / c

foo__mutmut_mutants = {
'foo__mutmut_1': foo__mutmut_1, 
    'foo__mutmut_2': foo__mutmut_2
}

def foo(*args, **kwargs):
    return _mutmut_trampoline(foo__mutmut_orig, foo__mutmut_mutants, *args, **kwargs) 

foo.__signature__ = _mutmut_signature(foo__mutmut_orig)
foo__mutmut_orig.__name__ = 'foo'


"""

    node = parse(source)
    result = ''.join([x[1] for x in yield_mutants_for_module(node, no_mutate_lines=[])])

    assert result == expected


def test_avoid_annotations():
    source = """
def foo(a: List[int]) -> int:
    return 1
"""

    expected = trampoline_impl + """

def foo__mutmut_orig(a: List[int]) -> int:
    return 1

def foo__mutmut_1(a: List[int]) -> int:
    return 2

foo__mutmut_mutants = {
'foo__mutmut_1': foo__mutmut_1
}

def foo(*args, **kwargs):
    return _mutmut_trampoline(foo__mutmut_orig, foo__mutmut_mutants, *args, **kwargs) 

foo.__signature__ = _mutmut_signature(foo__mutmut_orig)
foo__mutmut_orig.__name__ = 'foo'


"""

    node = parse(source)
    result = ''.join([x[1] for x in yield_mutants_for_module(node, no_mutate_lines=[])])

    assert result == expected
