from mutmut.trampoline_templates import trampoline_impl
from mutmut.file_mutation import mutate_file_contents

def mutated_module(source: str) -> str:
    mutated_code, _ = mutate_file_contents('', source)
    return mutated_code


def test_mutate_file_contents():
    source = """
a + 1

def foo(a, b, c):
    return a + b * c
"""
    trampolines = trampoline_impl.removesuffix('\n\n')

    expected = f"""
a + 1{trampolines}

def x_foo__mutmut_orig(a, b, c):
    return a + b * c

def x_foo__mutmut_1(a, b, c):
    return a - b * c

def x_foo__mutmut_2(a, b, c):
    return a + b / c

x_foo__mutmut_mutants : ClassVar[MutantDict] = {{
'x_foo__mutmut_1': x_foo__mutmut_1, 
    'x_foo__mutmut_2': x_foo__mutmut_2
}}

def foo(*args, **kwargs):
    result = _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs)
    return result 

foo.__signature__ = _mutmut_signature(x_foo__mutmut_orig)
x_foo__mutmut_orig.__name__ = 'x_foo'
"""

    result = mutated_module(source)

    assert result == expected


def test_avoid_annotations():
    source = """
def foo(a: List[int]) -> int:
    return 1
"""

    expected = trampoline_impl.removesuffix('\n\n') + """
def x_foo__mutmut_orig(a: List[int]) -> int:
    return 1
def x_foo__mutmut_1(a: List[int]) -> int:
    return 2

x_foo__mutmut_mutants : ClassVar[MutantDict] = {
'x_foo__mutmut_1': x_foo__mutmut_1
}

def foo(*args, **kwargs):
    result = _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs)
    return result 

foo.__signature__ = _mutmut_signature(x_foo__mutmut_orig)
x_foo__mutmut_orig.__name__ = 'x_foo'
"""

    result = mutated_module(source)

    assert result == expected
