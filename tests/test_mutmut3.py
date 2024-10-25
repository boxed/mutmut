from parso import parse

from mutmut.__main__ import (
    trampoline_impl,
    yield_from_trampoline_impl,
    yield_mutants_for_module,
)


def test_yield_mutants_for_module():
    source = """
a + 1

def foo(a, b, c):
    return a + b * c
"""

    expected = trampoline_impl + yield_from_trampoline_impl + """

a + 1

def x_foo__mutmut_orig(a, b, c):
    return a + b * c

def x_foo__mutmut_1(a, b, c):
    return a - b * c

def x_foo__mutmut_2(a, b, c):
    return a + b / c

x_foo__mutmut_mutants = {
'x_foo__mutmut_1': x_foo__mutmut_1, 
    'x_foo__mutmut_2': x_foo__mutmut_2
}

def foo(*args, **kwargs):
    result = _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, *args, **kwargs)
    return result 

foo.__signature__ = _mutmut_signature(x_foo__mutmut_orig)
x_foo__mutmut_orig.__name__ = 'x_foo'


"""

    node = parse(source)
    result = ''.join([x[1] for x in yield_mutants_for_module(node, no_mutate_lines=[])])

    assert result == expected


def test_avoid_annotations():
    source = """
def foo(a: List[int]) -> int:
    return 1
"""

    expected = trampoline_impl + yield_from_trampoline_impl + """

def x_foo__mutmut_orig(a: List[int]) -> int:
    return 1

def x_foo__mutmut_1(a: List[int]) -> int:
    return 2

x_foo__mutmut_mutants = {
'x_foo__mutmut_1': x_foo__mutmut_1
}

def foo(*args, **kwargs):
    result = _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, *args, **kwargs)
    return result 

foo.__signature__ = _mutmut_signature(x_foo__mutmut_orig)
x_foo__mutmut_orig.__name__ = 'x_foo'


"""

    node = parse(source)
    result = ''.join([x[1] for x in yield_mutants_for_module(node, no_mutate_lines=[])])

    assert result == expected
