from nootnoot.core.file_mutation import mutate_file_contents
from nootnoot.core.trampoline_templates import trampoline_impl


def mutated_module(source: str) -> str:
    mutated_code, _ = mutate_file_contents("", source)
    return mutated_code


def test_mutate_file_contents():
    source = """
a + 1

def foo(a, b, c):
    return a + b * c
"""
    trampolines = trampoline_impl.removesuffix("\n\n")

    expected = f"""
a + 1{trampolines}

def x_foo__nootnoot_orig(a, b, c):
    return a + b * c

def x_foo__nootnoot_1(a, b, c):
    return a - b * c

def x_foo__nootnoot_2(a, b, c):
    return a + b / c

x_foo__nootnoot_mutants : ClassVar[MutantDict] = {{
'x_foo__nootnoot_1': x_foo__nootnoot_1,
    'x_foo__nootnoot_2': x_foo__nootnoot_2
}}

def foo(*args, **kwargs):
    result = _nootnoot_trampoline(x_foo__nootnoot_orig, x_foo__nootnoot_mutants, args, kwargs)
    return result

foo.__signature__ = _nootnoot_signature(x_foo__nootnoot_orig)
x_foo__nootnoot_orig.__name__ = 'x_foo'
"""

    result = mutated_module(source)

    assert result == expected


def test_avoid_annotations():
    source = """
def foo(a: List[int]) -> int:
    return 1
"""

    expected = (
        trampoline_impl.removesuffix("\n\n")
        + """
def x_foo__nootnoot_orig(a: List[int]) -> int:
    return 1
def x_foo__nootnoot_1(a: List[int]) -> int:
    return 2

x_foo__nootnoot_mutants : ClassVar[MutantDict] = {
'x_foo__nootnoot_1': x_foo__nootnoot_1
}

def foo(*args, **kwargs):
    result = _nootnoot_trampoline(x_foo__nootnoot_orig, x_foo__nootnoot_mutants, args, kwargs)
    return result

foo.__signature__ = _nootnoot_signature(x_foo__nootnoot_orig)
x_foo__nootnoot_orig.__name__ = 'x_foo'
"""
    )

    result = mutated_module(source)

    assert result == expected
