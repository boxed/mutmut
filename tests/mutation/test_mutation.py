import os
from unittest.mock import Mock
from unittest.mock import patch

import libcst as cst
import pytest

from mutmut.__main__ import CatchOutput
from mutmut.__main__ import MutmutProgrammaticFailException
from mutmut.__main__ import get_diff_for_mutant
from mutmut.__main__ import orig_function_and_class_names_from_key
from mutmut.__main__ import run_forced_fail_test
from mutmut.mutation.file_mutation import create_mutations
from mutmut.mutation.file_mutation import mutate_file_contents
from mutmut.mutation.trampoline_templates import CLASS_NAME_SEPARATOR
from mutmut.mutation.trampoline_templates import mangle_function_name


def mutants_for_source(source: str, covered_lines: set[int] | None = None) -> list[str]:
    module, mutated_nodes, _, _ = create_mutations("test.py", source, covered_lines)
    mutants: list[str] = [module.deep_replace(m.original_node, m.mutated_node).code for m in mutated_nodes]  # type: ignore

    return mutants


def mutated_module(source: str) -> str:
    mutated_code, _ = mutate_file_contents("", source)
    return mutated_code


@pytest.mark.parametrize(
    "original, expected",
    [
        (
            "foo(a, *args, **kwargs)",
            [
                "foo(*args, **kwargs)",
                "foo(None, *args, **kwargs)",
                "foo(a, **kwargs)",
                "foo(a, *args, )",
            ],
        ),
        # ('break', 'continue'),  # probably a bad idea. Can introduce infinite loops.
        ("break", "return"),
        ("continue", "break"),
        ("a.lower()", "a.upper()"),
        ("a.upper()", "a.lower()"),
        ("a.b.lower()", "a.b.upper()"),
        ("a.b.upper()", "a.b.lower()"),
        ('a.lstrip("!")', ['a.rstrip("!")', 'a.lstrip("XX!XX")', "a.lstrip(None)"]),
        ('a.rstrip("!")', ['a.lstrip("!")', 'a.rstrip("XX!XX")', "a.rstrip(None)"]),
        ('a.find("!")', ['a.rfind("!")', 'a.find("XX!XX")', "a.find(None)"]),
        ('a.rfind("!")', ['a.find("!")', 'a.rfind("XX!XX")', "a.rfind(None)"]),
        (
            'a.ljust(10, "+")',
            [
                'a.ljust("+")',
                'a.ljust(10, "XX+XX")',
                "a.ljust(10, )",
                "a.ljust(10, None)",
                'a.ljust(11, "+")',
                'a.ljust(None, "+")',
                'a.rjust(10, "+")',
            ],
        ),
        (
            'a.rjust(10, "+")',
            [
                'a.ljust(10, "+")',
                'a.rjust("+")',
                'a.rjust(10, "XX+XX")',
                "a.rjust(10, )",
                "a.rjust(10, None)",
                'a.rjust(11, "+")',
                'a.rjust(None, "+")',
            ],
        ),
        ('a.index("+")', ['a.rindex("+")', 'a.index("XX+XX")', "a.index(None)"]),
        ('a.rindex("+")', ['a.index("+")', 'a.rindex("XX+XX")', "a.rindex(None)"]),
        ("a.split()", []),
        ("a.rsplit()", []),
        ('a.split(" ")', ['a.split("XX XX")', "a.split(None)"]),
        ('a.rsplit(" ")', ['a.rsplit("XX XX")', "a.rsplit(None)"]),
        ('a.split(sep="")', ['a.split(sep="XXXX")', "a.split(sep=None)"]),
        ('a.rsplit(sep="")', ['a.rsplit(sep="XXXX")', "a.rsplit(sep=None)"]),
        (
            "a.split(maxsplit=-1)",
            ["a.rsplit(maxsplit=-1)", "a.split(maxsplit=+1)", "a.split(maxsplit=-2)", "a.split(maxsplit=None)"],
        ),
        (
            "a.rsplit(maxsplit=-1)",
            ["a.split(maxsplit=-1)", "a.rsplit(maxsplit=+1)", "a.rsplit(maxsplit=-2)", "a.rsplit(maxsplit=None)"],
        ),
        (
            'a.split(" ", maxsplit=-1)',
            [
                'a.split(" ", )',
                'a.split(" ", maxsplit=+1)',
                'a.split(" ", maxsplit=-2)',
                'a.split(" ", maxsplit=None)',
                'a.split("XX XX", maxsplit=-1)',
                "a.split(None, maxsplit=-1)",
                "a.split(maxsplit=-1)",
                'a.rsplit(" ", maxsplit=-1)',
            ],
        ),
        (
            'a.rsplit(" ", maxsplit=-1)',
            [
                'a.rsplit(" ", )',
                'a.rsplit(" ", maxsplit=+1)',
                'a.rsplit(" ", maxsplit=-2)',
                'a.rsplit(" ", maxsplit=None)',
                'a.rsplit("XX XX", maxsplit=-1)',
                "a.rsplit(None, maxsplit=-1)",
                "a.rsplit(maxsplit=-1)",
                'a.split(" ", maxsplit=-1)',
            ],
        ),
        ("a.split(maxsplit=1)", ["a.split(maxsplit=2)", "a.split(maxsplit=None)", "a.rsplit(maxsplit=1)"]),
        ("a.rsplit(maxsplit=1)", ["a.rsplit(maxsplit=2)", "a.rsplit(maxsplit=None)", "a.split(maxsplit=1)"]),
        (
            'a.split(" ", 1)',
            [
                'a.rsplit(" ", 1)',
                'a.split(" ", )',
                'a.split(" ", 2)',
                'a.split(" ", None)',
                'a.split("XX XX", 1)',
                "a.split(1)",
                "a.split(None, 1)",
            ],
        ),
        (
            'a.rsplit(" ", 1)',
            [
                'a.rsplit(" ", )',
                'a.rsplit(" ", 2)',
                'a.rsplit(" ", None)',
                'a.rsplit("XX XX", 1)',
                "a.rsplit(1)",
                "a.rsplit(None, 1)",
                'a.split(" ", 1)',
            ],
        ),
        (
            'a.split(" ", maxsplit=1)',
            [
                'a.rsplit(" ", maxsplit=1)',
                'a.split(" ", )',
                'a.split(" ", maxsplit=2)',
                'a.split(" ", maxsplit=None)',
                'a.split("XX XX", maxsplit=1)',
                "a.split(None, maxsplit=1)",
                "a.split(maxsplit=1)",
            ],
        ),
        (
            'a.rsplit(" ", maxsplit=1)',
            [
                'a.rsplit(" ", )',
                'a.rsplit(" ", maxsplit=2)',
                'a.rsplit(" ", maxsplit=None)',
                'a.rsplit("XX XX", maxsplit=1)',
                "a.rsplit(None, maxsplit=1)",
                "a.rsplit(maxsplit=1)",
                'a.split(" ", maxsplit=1)',
            ],
        ),
        ('a.removeprefix("+")', ['a.removesuffix("+")', 'a.removeprefix("XX+XX")', "a.removeprefix(None)"]),
        ('a.removesuffix("+")', ['a.removeprefix("+")', 'a.removesuffix("XX+XX")', "a.removesuffix(None)"]),
        ('a.partition("++")', ['a.rpartition("++")', 'a.partition("XX++XX")', "a.partition(None)"]),
        ('a.rpartition("++")', ['a.partition("++")', 'a.rpartition("XX++XX")', "a.rpartition(None)"]),
        ("a(b)", "a(None)"),
        ("dict(a=None)", ["dict(aXX=None)"]),
        ("dict(a=b)", ["dict(aXX=b)", "dict(a=None)"]),
        (
            "lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(show=False)))",
            [
                "lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(show=True)))",
                "lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(show=None)))",
                "lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(showXX=False)))",
                "lambda **kwargs: Variable.integer(**setdefaults(None, dict(show=False)))",
                "lambda **kwargs: Variable.integer(**setdefaults(kwargs, None))",
                "lambda **kwargs: Variable.integer(**setdefaults(kwargs, ))",
                "lambda **kwargs: Variable.integer(**setdefaults(dict(show=False)))",
                # TODO: this mutant would exist if we also mutate single-arg arglists (see implementation)
                # 'lambda **kwargs: Variable.integer()',
                "lambda **kwargs: None",
            ],
        ),
        ("x: list[A | None]", []),
        ("a: Optional[int] = None", 'a: Optional[int] = ""'),
        ("a: int = 1", ["a: int = 2", "a: int = None"]),
        ('a: str = "FoO"', ['a: str = "XXFoOXX"', 'a: str = "foo"', 'a: str = "FOO"', "a: str = None"]),
        (r'a: str = "Fo\t"', [r'a: str = "XXFo\tXX"', r'a: str = "FO\t"', r'a: str = "fo\t"', "a: str = None"]),
        (
            r'a: str = "Fo\N{ghost} \U11223344"',
            [
                r'a: str = "XXFo\N{ghost} \U11223344XX"',
                r'a: str = "FO\N{GHOST} \U11223344"',
                r'a: str = "fo\N{ghost} \U11223344"',
                "a: str = None",
            ],
        ),
        ("lambda: 0", ["lambda: 1", "lambda: None"]),
        ("1 in (1, 2)", ["2 in (1, 2)", "1 not in (1, 2)", "1 in (2, 2)", "1 in (1, 3)"]),
        ("1+1", ["2+1", "1 - 1", "1+2"]),
        ("1", "2"),
        ("1-1", ["2-1", "1 + 1", "1-2"]),
        ("1*1", ["2*1", "1 / 1", "1*2"]),
        ("1/1", ["2/1", "1 * 1", "1/2"]),
        ("1//1", ["2//1", "1 / 1", "1//2"]),
        ("1%1", ["2%1", "1 / 1", "1%2"]),
        ("1<<1", ["2<<1", "1 >> 1", "1<<2"]),
        ("1>>1", ["2>>1", "1 << 1", "1>>2"]),
        ("a&b", ["a | b"]),
        ("a|b", ["a & b"]),
        ("a^b", ["a & b"]),
        ("a**b", ["a * b"]),
        ("~a", ["a"]),
        # ('1.0', '1.0000000000000002'),  # using numpy features
        ("1.0", "2.0"),
        ("0.1", "1.1"),
        ("1e-3", "1.001"),
        ("True", "False"),
        ("False", "True"),
        ('"FoO"', ['"XXFoOXX"', '"foo"', '"FOO"']),
        ("'FoO'", ["'XXFoOXX'", "'foo'", "'FOO'"]),
        ("u'FoO'", ["u'XXFoOXX'", "u'foo'", "u'FOO'"]),
        ("10", "11"),
        ("10.", "11.0"),
        ("0o10", "9"),
        ("0x10", "17"),
        ("0b10", "3"),
        ("1<2", ["2<2", "1 <= 2", "1<3"]),
        ("(1, 2)", ["(2, 2)", "(1, 3)"]),
        (
            "1 not in (1, 2)",
            ["2 not in (1, 2)", "1 in (1, 2)", "1 not in (2, 2)", "1 not in (1, 3)"],
        ),  # two spaces here because "not in" is two words
        ("foo is foo", "foo is not foo"),
        ("foo is not foo", "foo is foo"),
        ("a or b", "a and b"),
        ("a and b", "a or b"),
        ("not a", "a"),
        ("a < b", ["a <= b"]),
        ("a <= b", ["a < b"]),
        ("a > b", ["a >= b"]),
        ("a >= b", ["a > b"]),
        ("a == b", ["a != b"]),
        ("a != b", ["a == b"]),
        ("a = b", "a = None"),
        ("a = b = c = x", "a = b = c = None"),
        # subscript
        ("a[None]", []),
        ("a[b]", []),
        ("s[0]", ["s[1]"]),
        ("s[0] = a", ["s[1] = a", "s[0] = None"]),
        ("s[1:]", ["s[2:]"]),
        ("s[1:2]", ["s[2:2]", "s[1:3]"]),
        ("1j", "2j"),
        ("1.0j", "2j"),
        ("0o1", "2"),
        ("1.0e10", "10000000001.0"),
        ("a = {x for x in y}", "a = None"),
        ("x+=1", ["x = 1", "x -= 1", "x+=2"]),
        ("x-=1", ["x = 1", "x += 1", "x-=2"]),
        ("x*=1", ["x = 1", "x /= 1", "x*=2"]),
        ("x/=1", ["x = 1", "x *= 1", "x/=2"]),
        ("x//=1", ["x = 1", "x /= 1", "x//=2"]),
        ("x%=1", ["x = 1", "x /= 1", "x%=2"]),
        ("x<<=1", ["x = 1", "x >>= 1", "x<<=2"]),
        ("x>>=1", ["x = 1", "x <<= 1", "x>>=2"]),
        ("x&=1", ["x = 1", "x |= 1", "x&=2"]),
        ("x|=1", ["x = 1", "x &= 1", "x|=2"]),
        ("x^=1", ["x = 1", "x &= 1", "x^=2"]),
        ("x**=1", ["x = 1", "x *= 1", "x**=2"]),
        ("def foo(s: Int = 1): pass", "def foo(s: Int = 2): pass"),
        # mutating default args with function calls could cause Exceptions at import time
        ('def foo(a = A("abc")): pass', []),
        ("a = None", 'a = ""'),
        ("lambda **kwargs: None", "lambda **kwargs: 0"),
        ("lambda: None", "lambda: 0"),
        ("def foo(s: str): pass", []),
        ("def foo(a, *, b): pass", []),
        ("a(None)", []),
        ("'''foo'''", []),  # don't mutate things we assume to be docstrings
        ("r'''foo'''", []),  # don't mutate things we assume to be docstrings
        ('"""foo"""', []),  # don't mutate things we assume to be docstrings
        ("(x for x in [])", []),  # don't mutate 'in' in generators
        ("from foo import *", []),
        ("from .foo import *", []),
        ("import foo", []),
        ("import foo as bar", []),
        ("foo.bar", []),
        ("for x in y: pass", []),
        ("def foo(a, *args, **kwargs): pass", []),
        ("isinstance(a, b)", []),
        ("len(a)", []),
        ("deepcopy(obj)", ["copy(obj)", "deepcopy(None)"]),
    ],
)
def test_basic_mutations(original, expected):
    if isinstance(expected, str):
        expected = [expected]

    mutants = mutants_for_source(original)

    assert sorted(mutants) == sorted(expected)


def test_do_not_mutate_annotations():
    source = """
def foo() -> int:
    bar: Optional[int]
    return
    """.strip()

    mutants = mutants_for_source(source)
    for m in mutants:
        print(m)  # pragma: no cover

    assert not mutants


def test_do_not_mutate_specific_functions():
    source = """
class A:
    def __new__():
        return 1 + 2

    def __getattribute__():
        return 1 + 2

    def __setattr__():
        return 1 + 2
    """.strip()

    mutants = mutants_for_source(source)
    for m in mutants:
        print(m)  # pragma: no cover

    assert not mutants


def test_match_case():
    source = """
match x:
    case Point(x=1): return 1
    case _: return 2""".strip()

    mutants = mutants_for_source(source)

    expected = [
        """match x:\n    case Point(x=1): return 1""",
        """match x:\n    case _: return 2""",
        """match x:\n    case Point(x=2): return 1\n    case _: return 2""",
        """match x:\n    case Point(x=1): return 2\n    case _: return 2""",
        """match x:\n    case Point(x=1): return 1\n    case _: return 3""",
    ]

    assert sorted(mutants) == sorted(expected)


def test_mach_case_does_not_mutate_bitor():
    source = """
def concat():
    match x:
        case A() | B():
            pass
"""

    mutants = mutants_for_source(source)

    assert sorted(mutants) == []


def test_basic_class():
    source = """
class Foo:
    def member(self):
        return 1
    """.strip()

    mutated_code = mutated_module(source)

    expected = """
    def xǁFooǁmember__mutmut_orig(self):
        return 1
    def xǁFooǁmember__mutmut_1(self):
        return 2"""

    assert expected in mutated_code


def test_function_with_annotation():
    source = "def capitalize(s : str):\n    return s[0].title() + s[1:] if s else s\n".strip()

    mutated_code = mutated_module(source)
    print(mutated_code)

    expected_defs = [
        "def x_capitalize__mutmut_1(s : str):\n    return s[0].title() - s[1:] if s else s",
        "def x_capitalize__mutmut_2(s : str):\n    return s[1].title() + s[1:] if s else s",
        "def x_capitalize__mutmut_3(s : str):\n    return s[0].title() + s[2:] if s else s",
    ]

    for expected in expected_defs:
        print(expected)
        assert expected in mutated_code


def test_pragma_no_mutate():
    source = """def foo():\n    return 1+1  # pragma: no mutate\n""".strip()
    mutants = mutants_for_source(source)
    assert not mutants


def test_pragma_no_mutate_and_no_cover():
    source = """def foo():\n    return 1+1  # pragma: no cover, no mutate\n""".strip()
    mutants = mutants_for_source(source)
    assert not mutants


def test_pragma_no_mutate_on_function_definition():
    source = """
def foo(): # pragma: no mutate
    return 1+1"""
    mutants = mutants_for_source(source)
    assert mutants


def test_pragma_no_mutate_block_class():
    """Test that pragma: no mutate block skips entire class from mutation."""
    source = """
class Foo:  # pragma: no mutate block
    def method(self):
        return 1 + 1
""".strip()
    mutated_code = mutated_module(source)
    assert "xǁFooǁmethod__mutmut" not in mutated_code
    assert "def method(self):" in mutated_code
    assert "return 1 + 1" in mutated_code


def test_pragma_no_mutate_block_class_with_colon():
    """Test that pragma: no mutate: block also works (alternative syntax)."""
    source = """
class Bar:  # pragma: no mutate: block
    def method(self):
        return 2 + 2
""".strip()
    mutated_code = mutated_module(source)
    assert "xǁBarǁmethod__mutmut" not in mutated_code
    assert "def method(self):" in mutated_code


def test_pragma_no_mutate_block_does_not_affect_other_classes():
    """Test that pragma: no mutate block only affects the annotated class."""
    source = """
class Skipped:  # pragma: no mutate block
    def method(self):
        return 1

class Mutated:
    def method(self):
        return 1
""".strip()
    mutated_code = mutated_module(source)
    assert "xǁSkippedǁmethod__mutmut" not in mutated_code
    assert "xǁMutatedǁmethod__mutmut_orig" in mutated_code


def test_pragma_no_mutate_vs_no_mutate_block_class():
    """Test that regular pragma: no mutate does NOT skip entire class (only that line)."""
    source = """
class Foo:  # pragma: no mutate
    def method(self):
        return 1 + 1
""".strip()
    mutated_code = mutated_module(source)
    assert "xǁFooǁmethod__mutmut" in mutated_code


def test_pragma_no_mutate_block_enum():
    """Test the enum use case - block pragma prevents trampoline attribute injection."""
    source = """
from enum import Enum

class Color(Enum):  # pragma: no mutate block
    RED = 1
    GREEN = 2

    def describe(self):
        return self.name.lower()
""".strip()
    mutated_code = mutated_module(source)
    assert "__mutmut_mutants" not in mutated_code
    assert "xǁColorǁdescribe__mutmut" not in mutated_code
    assert "class Color(Enum):" in mutated_code
    assert "RED = 1" in mutated_code


def test_pragma_no_mutate_block_function():
    """Test that pragma: no mutate block skips entire function from mutation."""
    source = """
def foo():  # pragma: no mutate block
    return 1 + 1
""".strip()
    mutated_code = mutated_module(source)
    assert "x_foo__mutmut" not in mutated_code
    assert "__mutmut_mutants" not in mutated_code
    assert "def foo():" in mutated_code
    assert "return 1 + 1" in mutated_code


def test_pragma_no_mutate_block_function_with_colon():
    """Test that pragma: no mutate: block also works for functions."""
    source = """
def bar():  # pragma: no mutate: block
    return 2 + 2
""".strip()
    mutated_code = mutated_module(source)
    assert "x_bar__mutmut" not in mutated_code
    assert "def bar():" in mutated_code


def test_pragma_no_mutate_block_does_not_affect_other_functions():
    """Test that pragma: no mutate block only affects the annotated function."""
    source = """
def skipped():  # pragma: no mutate block
    return 1

def mutated():
    return 1
""".strip()
    mutated_code = mutated_module(source)
    assert "x_skipped__mutmut" not in mutated_code
    assert "x_mutated__mutmut_orig" in mutated_code


def test_pragma_no_mutate_vs_no_mutate_block_function():
    """Test that regular pragma: no mutate does NOT skip entire function."""
    source = """
def foo():  # pragma: no mutate
    return 1 + 1
""".strip()
    mutated_code = mutated_module(source)
    assert "x_foo__mutmut" in mutated_code


def test_pragma_no_mutate_block_standalone_body_only():
    """Standalone block pragma inside a function body suppresses the body
    but leaves the def line (including default args) mutable."""
    source = """
def buzz(val=1):
    # pragma: no mutate block
    return val + 1
""".strip()
    mutated_code = mutated_module(source)
    assert "x_buzz__mutmut_orig" in mutated_code
    assert "return val + 1" in mutated_code


def test_pragma_no_mutate_block_inline_if_allows_elif():
    """Inline block pragma on an if-statement suppresses only that branch;
    the elif/else branches remain mutable because they exit the if scope."""
    source = """
def top_level(a, b):
    if a > b:  # pragma: no mutate block
        return a
    elif b > a:
        return b
    return a + b
""".strip()
    mutated_code = mutated_module(source)
    assert "x_top_level__mutmut_orig" in mutated_code
    # elif condition IS mutated (b > a -> b >= a)
    assert "b >= a" in mutated_code
    # if condition is NOT mutated (suppressed by inline block pragma)
    assert "a >= b" not in mutated_code


def test_pragma_no_mutate_start_end_function():
    """Test that start/end markers suppress all mutations within a function."""
    source = """
# pragma: no mutate start
def foo():
    return 1 + 1
# pragma: no mutate end
""".strip()
    mutated_code = mutated_module(source)
    assert "x_foo__mutmut" not in mutated_code
    assert "__mutmut_mutants" not in mutated_code
    assert "def foo():" in mutated_code
    assert "return 1 + 1" in mutated_code


def test_pragma_no_mutate_start_end_does_not_affect_outside():
    """Test that code outside start/end markers is still mutated."""
    source = """
# pragma: no mutate start
def skipped():
    return 1 + 1
# pragma: no mutate end

def mutated():
    return 1 + 1
""".strip()
    mutated_code = mutated_module(source)
    assert "x_skipped__mutmut" not in mutated_code
    assert "x_mutated__mutmut_orig" in mutated_code


def test_pragma_no_mutate_start_end_class_method():
    """Test that start/end inside a class suppresses only the wrapped method."""
    source = """
class Foo:
    # pragma: no mutate start
    def skipped(self):
        return 1 + 1
    # pragma: no mutate end

    def mutated(self):
        return 1 + 1
""".strip()
    mutated_code = mutated_module(source)
    assert "xǁFooǁskipped__mutmut" not in mutated_code
    assert "xǁFooǁmutated__mutmut_orig" in mutated_code


def test_pragma_no_mutate_start_end_partial_function():
    """Test that start/end around part of a function suppresses only those lines."""
    source = """
def foo():
    x = 1 + 1
    # pragma: no mutate start
    y = 2 + 2
    # pragma: no mutate end
    z = 3 + 3
""".strip()
    mutated_code = mutated_module(source)
    assert "x_foo__mutmut_orig" in mutated_code
    assert "1 + 1" not in mutated_code or "x_foo__mutmut" in mutated_code
    assert "3 + 3" not in mutated_code or "x_foo__mutmut" in mutated_code


def test_enum_mutation_uses_external_injection():
    """Test that enum classes use external injection pattern to avoid metaclass conflicts."""
    source = """
from enum import Enum

class Color(Enum):
    RED = 1
    GREEN = 2

    def describe(self):
        return self.name.lower()
""".strip()
    mutated_code = mutated_module(source)
    # Should NOT have mutant attributes injected INTO the class body (breaks enums)
    # The mutant dict should be OUTSIDE the class (before the class definition)
    assert "_Color_describe_mutants" in mutated_code
    # External trampoline function should exist
    assert "_Color_describe_trampoline" in mutated_code
    # The method inside the class should be a simple assignment
    assert "describe = _Color_describe_trampoline" in mutated_code
    # Ensure no ClassVar inside the class (which would break enum)
    # Split to get just the class body
    class_start = mutated_code.find("class Color(Enum):")
    assert class_start > mutated_code.find("_Color_describe_mutants")  # mutants dict is BEFORE class


def test_enum_mutation_with_staticmethod():
    """Test that @staticmethod in enum classes works correctly."""
    source = """
from enum import Enum

class Color(Enum):
    RED = 1

    @staticmethod
    def helper():
        return 1 + 1
""".strip()
    mutated_code = mutated_module(source)
    # Should have external trampoline
    assert "_Color_helper_trampoline" in mutated_code
    # Assignment should use staticmethod wrapper
    assert "helper = staticmethod(_Color_helper_trampoline)" in mutated_code


def test_enum_mutation_with_classmethod():
    """Test that @classmethod in enum classes works correctly."""
    source = """
from enum import Enum

class Color(Enum):
    RED = 1

    @classmethod
    def from_string(cls):
        return 1 + 1
""".strip()
    mutated_code = mutated_module(source)
    # Should have external trampoline
    assert "_Color_from_string_trampoline" in mutated_code
    # Assignment should use classmethod wrapper
    assert "from_string = classmethod(_Color_from_string_trampoline)" in mutated_code


def test_enum_mutation_preserves_enum_members():
    """Test that enum members are preserved when methods are mutated."""
    source = """
from enum import Enum

class Status(Enum):
    PENDING = 'pending'
    ACTIVE = 'active'
    DONE = 'done'

    def is_active(self):
        return self == Status.ACTIVE
""".strip()
    mutated_code = mutated_module(source)
    # Enum members should be unchanged
    assert "PENDING = 'pending'" in mutated_code
    assert "ACTIVE = 'active'" in mutated_code
    assert "DONE = 'done'" in mutated_code
    # But method should be mutated externally
    assert "_Status_is_active_trampoline" in mutated_code


def test_regular_class_staticmethod_mutation():
    """Test that @staticmethod in regular classes is now mutated using external injection."""
    source = """
class Calculator:
    @staticmethod
    def add(a, b):
        return a + b
""".strip()
    mutated_code = mutated_module(source)
    # Should use external injection pattern
    assert "_Calculator_add_trampoline" in mutated_code
    assert "_Calculator_add_orig" in mutated_code
    # Assignment should use staticmethod wrapper
    assert "add = staticmethod(_Calculator_add_trampoline)" in mutated_code


def test_regular_class_classmethod_mutation():
    """Test that @classmethod in regular classes is now mutated using external injection."""
    source = """
class Factory:
    @classmethod
    def create(cls, value):
        return value + 1
""".strip()
    mutated_code = mutated_module(source)
    # Should use external injection pattern
    assert "_Factory_create_trampoline" in mutated_code
    assert "_Factory_create_orig" in mutated_code
    # Assignment should use classmethod wrapper
    assert "create = classmethod(_Factory_create_trampoline)" in mutated_code


def test_regular_class_mixed_methods():
    """Test that regular classes correctly handle mix of instance, static, and class methods."""
    source = """
class MyClass:
    def instance_method(self):
        return 1 + 1

    @staticmethod
    def static_method():
        return 2 + 2

    @classmethod
    def class_method(cls):
        return 3 + 3
""".strip()
    mutated_code = mutated_module(source)
    # Instance method uses internal trampoline (inside class)
    assert "xǁMyClassǁinstance_method__mutmut_orig" in mutated_code
    # Static and class methods use external injection
    assert "_MyClass_static_method_trampoline" in mutated_code
    assert "_MyClass_class_method_trampoline" in mutated_code
    assert "static_method = staticmethod(_MyClass_static_method_trampoline)" in mutated_code
    assert "class_method = classmethod(_MyClass_class_method_trampoline)" in mutated_code


def test_mutate_only_covered_lines_none():
    source = """def foo():\n    return 1+1\n""".strip()
    mutants = mutants_for_source(source, covered_lines=set())
    assert not mutants


def test_mutate_only_covered_lines_all():
    source = """def foo():\n    return 1+1\n""".strip()
    mutants_expected = mutants_for_source(source)
    mutants = mutants_for_source(source, covered_lines=set([1, 2]))
    assert mutants
    assert mutants == mutants_expected


def test_mutate_dict():
    source = "dict(a=b, c=d)"

    mutants = mutants_for_source(source)

    expected = [
        "dict(a=None, c=d)",
        "dict(aXX=b, c=d)",
        "dict(a=b, c=None)",
        "dict(a=b, cXX=d)",
        "dict(c=d)",
        "dict(a=b, )",
    ]

    assert sorted(mutants) == sorted(expected)


def test_syntax_error():
    with pytest.raises(cst.ParserSyntaxError):
        mutate_file_contents("some_file.py", ":!")


def test_bug_github_issue_18():
    source = """
@register.simple_tag(name='icon')
def icon(name):
    if name is None:
        return ''
    tpl = '<span class="glyphicon glyphicon-{}"></span>'
    return format_html(tpl, name)
    """.strip()
    mutants_for_source(source)


def test_bug_github_issue_19_argument_mutation_crash():
    source = """key = lambda a: "foo"
filters = dict((key(field), False) for field in fields)"""
    mutants_for_source(source)


def test_bug_github_issue_26():
    source = """
def wrapper():
    class ConfigurationOptions(Protocol):
        min_name_length: int
    """.strip()
    assert mutants_for_source(source) == []


def test_bug_github_issue_30():
    source = """
def wrapper():
    def from_checker(cls: Type['BaseVisitor'], checker) -> 'BaseVisitor':
        pass
    """.strip()
    assert mutants_for_source(source) == []


def test_bug_github_issue_77():
    # Don't crash on this
    assert mutants_for_source("") == []


def test_bug_github_issue_435():
    source = r"""
    def parse(self, text: str) -> tuple[Tree[Token], str]:
        text = re.sub(r'[\w\-]  [\w\-]', dashrepl, text)

        return self.parser.parse(text), text
    """.strip()

    mutants = mutants_for_source(source)

    expected = [
        "def parse(self, text: str) -> tuple[Tree[Token], str]:\n        text = None\n\n        return self.parser.parse(text), text",
        "def parse(self, text: str) -> tuple[Tree[Token], str]:\n        text = re.sub(None, dashrepl, text)\n\n        return self.parser.parse(text), text",
        "def parse(self, text: str) -> tuple[Tree[Token], str]:\n        text = re.sub(r'[\\w\\-]  [\\w\\-]', None, text)\n\n        return self.parser.parse(text), text",
        "def parse(self, text: str) -> tuple[Tree[Token], str]:\n        text = re.sub(r'[\\w\\-]  [\\w\\-]', dashrepl, None)\n\n        return self.parser.parse(text), text",
        "def parse(self, text: str) -> tuple[Tree[Token], str]:\n        text = re.sub(dashrepl, text)\n\n        return self.parser.parse(text), text",
        "def parse(self, text: str) -> tuple[Tree[Token], str]:\n        text = re.sub(r'[\\w\\-]  [\\w\\-]', text)\n\n        return self.parser.parse(text), text",
        "def parse(self, text: str) -> tuple[Tree[Token], str]:\n        text = re.sub(r'[\\w\\-]  [\\w\\-]', dashrepl, )\n\n        return self.parser.parse(text), text",
        "def parse(self, text: str) -> tuple[Tree[Token], str]:\n        text = re.sub(r'XX[\\w\\-]  [\\w\\-]XX', dashrepl, text)\n\n        return self.parser.parse(text), text",
        "def parse(self, text: str) -> tuple[Tree[Token], str]:\n        text = re.sub(r'[\\w\\-]  [\\w\\-]', dashrepl, text)\n\n        return self.parser.parse(None), text",
    ]
    assert sorted(mutants) == sorted(expected)


def test_multiline_dunder_whitelist():
    source = """
__all__ = [
    1,
    2,
    'foo',
    'bar',
]
    """.strip()
    mutated_code = mutated_module(source)
    assert source in mutated_code


def test_bad_mutation_str_type_definition():
    source = """
def foo():
    foo: 'SomeType'
""".strip()
    mutants = mutants_for_source(source)
    assert not mutants


def test_orig_function_name_from_key():
    assert orig_function_and_class_names_from_key(f"_{CLASS_NAME_SEPARATOR}Foo{CLASS_NAME_SEPARATOR}bar__mutmut_1") == (
        "bar",
        "Foo",
    )
    assert orig_function_and_class_names_from_key("x_bar__mutmut_1") == ("bar", None)


def test_mangle_function_name():
    assert mangle_function_name(name="bar", class_name=None) == "x_bar"
    assert mangle_function_name(name="bar", class_name="Foo") == f"x{CLASS_NAME_SEPARATOR}Foo{CLASS_NAME_SEPARATOR}bar"


def test_diff_ops():
    source = """
def foo():
    return 1


class Foo:
    def member(self):
        return 3

    """.strip()

    mutants_source, mutant_names = mutate_file_contents("filename", source)
    assert len(mutant_names) == 2

    diff1 = get_diff_for_mutant(mutant_name=mutant_names[0], source=mutants_source, path="test.py").strip()
    diff2 = get_diff_for_mutant(mutant_name=mutant_names[1], source=mutants_source, path="test.py").strip()

    assert (
        diff1
        == """
--- test.py
+++ test.py
@@ -1,2 +1,2 @@
 def foo():
-    return 1
+    return 2
""".strip()
    )

    assert (
        diff2
        == """
--- test.py
+++ test.py
@@ -1,2 +1,2 @@
 def member(self):
-    return 3
+    return 4
""".strip()
    )


def test_from_future_still_first():
    source = """
from __future__ import annotations
from collections.abc import Iterable

def foo():
    return 1
""".strip()
    mutated_source = mutated_module(source)
    assert mutated_source.split("\n")[0] == "from __future__ import annotations"
    assert mutated_source.count("from __future__") == 1


def test_from_future_with_docstring_still_first():
    source = """
'''This documents the module'''
from __future__ import annotations
from collections.abc import Iterable

def foo():
    return 1
""".strip()
    mutated_source = mutated_module(source)
    assert mutated_source.split("\n")[0] == "'''This documents the module'''"
    assert mutated_source.split("\n")[1] == "from __future__ import annotations"
    assert mutated_source.count("from __future__") == 1


# Negate the effects of CatchOutput because it does not play nicely with capfd in GitHub Actions
@patch.object(CatchOutput, "dump_output")
@patch.object(CatchOutput, "stop")
@patch.object(CatchOutput, "start")
def test_run_forced_fail_test_with_failing_test(_start, _stop, _dump_output, capfd):
    runner = _mocked_runner_run_forced_failed(return_value=1)

    run_forced_fail_test(runner)

    out, err = capfd.readouterr()

    print()
    print(f"out: {out}")
    print(f"err: {err}")
    assert "done" in out
    assert not os.environ["MUTANT_UNDER_TEST"]


# Negate the effects of CatchOutput because it does not play nicely with capfd in GitHub Actions
@patch.object(CatchOutput, "dump_output")
@patch.object(CatchOutput, "stop")
@patch.object(CatchOutput, "start")
def test_run_forced_fail_test_with_mutmut_programmatic_fail_exception(_start, _stop, _dump_output, capfd):
    runner = _mocked_runner_run_forced_failed(side_effect=MutmutProgrammaticFailException())

    run_forced_fail_test(runner)

    out, _ = capfd.readouterr()
    assert "done" in out
    assert not os.environ["MUTANT_UNDER_TEST"]


# Negate the effects of CatchOutput because it does not play nicely with capfd in GitHub Actions
@patch.object(CatchOutput, "dump_output")
@patch.object(CatchOutput, "stop")
@patch.object(CatchOutput, "start")
def test_run_forced_fail_test_with_all_tests_passing(_start, _stop, _dump_output, capfd):
    runner = _mocked_runner_run_forced_failed(return_value=0)

    with pytest.raises(SystemExit) as error:
        run_forced_fail_test(runner)

    assert error.value.code == 1
    out, _ = capfd.readouterr()
    assert "FAILED: Unable to force test failures" in out


def _mocked_runner_run_forced_failed(return_value=None, side_effect=None):
    runner = Mock()
    runner.run_forced_fail = Mock(return_value=return_value, side_effect=side_effect)
    return runner


def test_do_not_mutate_top_level_decorators():
    # Modifying top-level decorators could influence all mutations
    # because they are executed at import time
    source = """
@some_decorator(a = 2)
def foo():
    x = 1 + 2
    return x

@unique
class A(Enum):
    @property
    def x(self):
        return 1 + 2
""".strip()

    mutants = mutants_for_source(source)
    for m in mutants:
        print(m)  # pragma: no cover

    assert not mutants


@pytest.mark.skip(reason="Feature not yet implemented")
def test_decorated_inner_functions_mutation():
    source = """
def foo():
    @decorator
    def inner():
        pass""".strip()

    expected = """
def x_foo__mutmut_1():

    def inner():
        pass""".strip()

    mutants = mutants_for_source(source)
    assert mutants == [expected]
