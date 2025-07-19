import os
from unittest.mock import Mock, patch
import pytest
import libcst as cst

import mutmut
from mutmut.__main__ import (
    CLASS_NAME_SEPARATOR,
    get_diff_for_mutant,
    orig_function_and_class_names_from_key,
    run_forced_fail_test,
    Config,
    MutmutProgrammaticFailException,
    CatchOutput,
)
from mutmut.trampoline_templates import trampoline_impl, mangle_function_name
from mutmut.file_mutation import create_mutations, mutate_file_contents

def mutants_for_source(source: str) -> list[str]:
    module, mutated_nodes = create_mutations(source)
    mutants: list[str] = []
    for m in mutated_nodes:
        mutants.append(module.deep_replace(m.original_node, m.mutated_node).code)  # type: ignore

    return mutants

def mutated_module(source: str) -> str:
    mutated_code, _ = mutate_file_contents('', source)
    return mutated_code


@pytest.mark.parametrize(
    'original, expected', [
        ('foo(a, *args, **kwargs)', [
            'foo(*args, **kwargs)',
            'foo(None, *args, **kwargs)',
            'foo(a, **kwargs)',
            'foo(a, *args, )',
        ]),
        # ('break', 'continue'),  # probably a bad idea. Can introduce infinite loops.
        ('break', 'return'),
        ('continue', 'break'),
        ('a.lower()', 'a.upper()'),
        ('a.upper()', 'a.lower()'),
        ('a.b.lower()', 'a.b.upper()'),
        ('a.b.upper()', 'a.b.lower()'),
        ('a.lstrip("!")', ['a.rstrip("!")', 'a.lstrip("XX!XX")', 'a.lstrip(None)']),
        ('a.rstrip("!")', ['a.lstrip("!")', 'a.rstrip("XX!XX")', 'a.rstrip(None)']),
        ('a.find("!")', ['a.rfind("!")', 'a.find("XX!XX")', 'a.find(None)']),
        ('a.rfind("!")', ['a.find("!")', 'a.rfind("XX!XX")', 'a.rfind(None)']),
        ('a.ljust(10, "+")', [
            'a.ljust("+")', 'a.ljust(10, "XX+XX")',
            'a.ljust(10, )', 'a.ljust(10, None)',
            'a.ljust(11, "+")', 'a.ljust(None, "+")',
            'a.rjust(10, "+")'
        ]),
        ('a.rjust(10, "+")', [
            'a.ljust(10, "+")', 'a.rjust("+")',
            'a.rjust(10, "XX+XX")', 'a.rjust(10, )',
            'a.rjust(10, None)', 'a.rjust(11, "+")',
            'a.rjust(None, "+")'
        ]),
        ('a.index("+")', ['a.rindex("+")', 'a.index("XX+XX")', 'a.index(None)']),
        ('a.rindex("+")', ['a.index("+")', 'a.rindex("XX+XX")', 'a.rindex(None)']),
        ('a.split()', []),
        ('a.rsplit()', []),
        ('a.split(" ")', ['a.split("XX XX")', 'a.split(None)']),
        ('a.rsplit(" ")', ['a.rsplit("XX XX")', 'a.rsplit(None)']),
        ('a.split(sep="")', ['a.split(sep="XXXX")', 'a.split(sep=None)']),
        ('a.rsplit(sep="")', ['a.rsplit(sep="XXXX")', 'a.rsplit(sep=None)']),
        ('a.split(maxsplit=-1)', [
            'a.rsplit(maxsplit=-1)', 'a.split(maxsplit=+1)', 'a.split(maxsplit=-2)', 'a.split(maxsplit=None)'
        ]),
        ('a.rsplit(maxsplit=-1)', [
            'a.split(maxsplit=-1)', 'a.rsplit(maxsplit=+1)', 'a.rsplit(maxsplit=-2)', 'a.rsplit(maxsplit=None)'
        ]),
        ('a.split(" ", maxsplit=-1)', [
            'a.split(" ", )', 'a.split(" ", maxsplit=+1)', 'a.split(" ", maxsplit=-2)',
            'a.split(" ", maxsplit=None)', 'a.split("XX XX", maxsplit=-1)', 'a.split(None, maxsplit=-1)',
            'a.split(maxsplit=-1)', 'a.rsplit(" ", maxsplit=-1)'
        ]),
        ('a.rsplit(" ", maxsplit=-1)', [
            'a.rsplit(" ", )', 'a.rsplit(" ", maxsplit=+1)', 'a.rsplit(" ", maxsplit=-2)',
            'a.rsplit(" ", maxsplit=None)', 'a.rsplit("XX XX", maxsplit=-1)', 'a.rsplit(None, maxsplit=-1)',
            'a.rsplit(maxsplit=-1)', 'a.split(" ", maxsplit=-1)'
        ]),
        ('a.split(maxsplit=1)', ['a.split(maxsplit=2)', 'a.split(maxsplit=None)', 'a.rsplit(maxsplit=1)']),
        ('a.rsplit(maxsplit=1)', ['a.rsplit(maxsplit=2)', 'a.rsplit(maxsplit=None)', 'a.split(maxsplit=1)']),
        ('a.split(" ", 1)', [
            'a.rsplit(" ", 1)', 'a.split(" ", )', 'a.split(" ", 2)', 'a.split(" ", None)',
            'a.split("XX XX", 1)', 'a.split(1)', 'a.split(None, 1)'
        ]),
        ('a.rsplit(" ", 1)', [
            'a.rsplit(" ", )', 'a.rsplit(" ", 2)', 'a.rsplit(" ", None)', 'a.rsplit("XX XX", 1)',
            'a.rsplit(1)', 'a.rsplit(None, 1)', 'a.split(" ", 1)'
        ]),
        ('a.split(" ", maxsplit=1)', [
            'a.rsplit(" ", maxsplit=1)', 'a.split(" ", )', 'a.split(" ", maxsplit=2)', 'a.split(" ", maxsplit=None)',
            'a.split("XX XX", maxsplit=1)', 'a.split(None, maxsplit=1)', 'a.split(maxsplit=1)'
        ]),
        ('a.rsplit(" ", maxsplit=1)', [
            'a.rsplit(" ", )', 'a.rsplit(" ", maxsplit=2)', 'a.rsplit(" ", maxsplit=None)',
            'a.rsplit("XX XX", maxsplit=1)', 'a.rsplit(None, maxsplit=1)', 'a.rsplit(maxsplit=1)',
            'a.split(" ", maxsplit=1)'
        ]),
        ('a.removeprefix("+")', ['a.removesuffix("+")', 'a.removeprefix("XX+XX")', 'a.removeprefix(None)']),
        ('a.removesuffix("+")', ['a.removeprefix("+")', 'a.removesuffix("XX+XX")', 'a.removesuffix(None)']),
        ('a.partition("++")', ['a.rpartition("++")', 'a.partition("XX++XX")', 'a.partition(None)']),
        ('a.rpartition("++")', ['a.partition("++")', 'a.rpartition("XX++XX")', 'a.rpartition(None)']),
        ('a(b)', 'a(None)'),
        ("dict(a=None)", ["dict(aXX=None)"]),
        ("dict(a=b)", ["dict(aXX=b)", 'dict(a=None)']),
        ('lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(show=False)))', [
            'lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(show=True)))',
            'lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(show=None)))',
            'lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(showXX=False)))',
            'lambda **kwargs: Variable.integer(**setdefaults(None, dict(show=False)))',
            'lambda **kwargs: Variable.integer(**setdefaults(kwargs, None))',
            'lambda **kwargs: Variable.integer(**setdefaults(kwargs, ))',
            'lambda **kwargs: Variable.integer(**setdefaults(dict(show=False)))',
            # TODO: this mutant would exist if we also mutate single-arg arglists (see implentation)
            # 'lambda **kwargs: Variable.integer()',
            'lambda **kwargs: None',
        ]),
        ('x: list[A | None]', []),
        ('a: Optional[int] = None', 'a: Optional[int] = ""'),
        ('a: int = 1', ['a: int = 2', 'a: int = None']),
        ('a: str = "FoO"', ['a: str = "XXFoOXX"', 'a: str = "foo"', 'a: str = "FOO"', 'a: str = None']),
        (r'a: str = "Fo\t"', [r'a: str = "XXFo\tXX"', r'a: str = "FO\t"', r'a: str = "fo\t"', 'a: str = None']),
        (r'a: str = "Fo\N{ghost} \U11223344"', [r'a: str = "XXFo\N{ghost} \U11223344XX"', r'a: str = "FO\N{GHOST} \U11223344"', r'a: str = "fo\N{ghost} \U11223344"', 'a: str = None']),
        ('lambda: 0', ['lambda: 1', 'lambda: None']),
        ("1 in (1, 2)", ['2 in (1, 2)', '1 not in (1, 2)', '1 in (2, 2)', '1 in (1, 3)']),
        ('1+1', ['2+1', '1 - 1', '1+2']),
        ('1', '2'),
        ('1-1', ['2-1', '1 + 1', '1-2']),
        ('1*1', ['2*1', '1 / 1', '1*2']),
        ('1/1', ['2/1', '1 * 1', '1/2']),
        ('1//1', ['2//1', '1 / 1', '1//2']),
        ('1%1', ['2%1', '1 / 1', '1%2']),
        ('1<<1', ['2<<1', '1 >> 1', '1<<2']),
        ('1>>1', ['2>>1', '1 << 1', '1>>2']),
        ('a&b', ['a | b']),
        ('a|b', ['a & b']),
        ('a^b', ['a & b']),
        ('a**b', ['a * b']),
        ('~a', ['a']),
        # ('1.0', '1.0000000000000002'),  # using numpy features
        ('1.0', '2.0'),
        ('0.1', '1.1'),
        ('1e-3', '1.001'),
        ('True', 'False'),
        ('False', 'True'),
        ('"FoO"', ['"XXFoOXX"', '"foo"', '"FOO"']),
        ("'FoO'", ["'XXFoOXX'", "'foo'", "'FOO'"]),
        ("u'FoO'", ["u'XXFoOXX'", "u'foo'", "u'FOO'"]),
        ("10", "11"),
        ("10.", "11.0"),
        ("0o10", "9"),
        ("0x10", "17"),
        ("0b10", "3"),
        ("1<2", ['2<2', '1 <= 2', '1<3']),
        ('(1, 2)', ['(2, 2)', '(1, 3)']),
        ("1 not in (1, 2)", ['2 not in (1, 2)', '1 in (1, 2)', '1 not in (2, 2)', '1 not in (1, 3)']),  # two spaces here because "not in" is two words
        ("foo is foo", "foo is not foo"),
        ("foo is not foo", "foo is foo"),
        ('a or b', 'a and b'),
        ('a and b', 'a or b'),
        ('not a', 'a'),
        ('a < b', ['a <= b']),
        ('a <= b', ['a < b']),
        ('a > b', ['a >= b']),
        ('a >= b', ['a > b']),
        ('a == b', ['a != b']),
        ('a != b', ['a == b']),
        ('a = b', 'a = None'),
        ('a = b = c = x', 'a = b = c = None'),

        # subscript
        ('a[None]', []),
        ('a[b]', []),
        ('s[0]', ['s[1]']),
        ('s[0] = a', ['s[1] = a', 's[0] = None']),
        ('s[1:]', ['s[2:]']),
        ('s[1:2]', ['s[2:2]', 's[1:3]']),

        ('1j', '2j'),
        ('1.0j', '2j'),
        ('0o1', '2'),
        ('1.0e10', '10000000001.0'),
        ('a = {x for x in y}', 'a = None'),
        ('x+=1', ['x = 1', 'x -= 1', 'x+=2']),
        ('x-=1', ['x = 1', 'x += 1', 'x-=2']),
        ('x*=1', ['x = 1', 'x /= 1', 'x*=2']),
        ('x/=1', ['x = 1', 'x *= 1', 'x/=2']),
        ('x//=1', ['x = 1', 'x /= 1', 'x//=2']),
        ('x%=1', ['x = 1', 'x /= 1', 'x%=2']),
        ('x<<=1', ['x = 1', 'x >>= 1', 'x<<=2']),
        ('x>>=1', ['x = 1', 'x <<= 1', 'x>>=2']),
        ('x&=1', ['x = 1', 'x |= 1', 'x&=2']),
        ('x|=1', ['x = 1', 'x &= 1', 'x|=2']),
        ('x^=1', ['x = 1', 'x &= 1', 'x^=2']),
        ('x**=1', ['x = 1', 'x *= 1', 'x**=2']),
        ('def foo(s: Int = 1): pass', 'def foo(s: Int = 2): pass'),
        # mutating default args with function calls could cause Exceptions at import time
        ('def foo(a = A("abc")): pass', []),
        ('a = None', 'a = ""'),
        ('lambda **kwargs: None', 'lambda **kwargs: 0'),
        ('lambda: None', 'lambda: 0'),
        ('def foo(s: str): pass', []),
        ('def foo(a, *, b): pass', []),
        ('a(None)', []),
        ("'''foo'''", []),  # don't mutate things we assume to be docstrings
        ("r'''foo'''", []),  # don't mutate things we assume to be docstrings
        ('"""foo"""', []),  # don't mutate things we assume to be docstrings
        ('(x for x in [])', []),  # don't mutate 'in' in generators
        ('from foo import *', []),
        ('from .foo import *', []),
        ('import foo', []),
        ('import foo as bar', []),
        ('foo.bar', []),
        ('for x in y: pass', []),
        ('def foo(a, *args, **kwargs): pass', []),
        ('import foo', []),
        ('isinstance(a, b)', []),
        ('len(a)', []),
        ('deepcopy(obj)', ['copy(obj)', 'deepcopy(None)']),
    ]
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

    expected = """class Foo:
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
        'def x_capitalize__mutmut_1(s : str):\n    return s[0].title() - s[1:] if s else s',
        'def x_capitalize__mutmut_2(s : str):\n    return s[1].title() + s[1:] if s else s',
        'def x_capitalize__mutmut_3(s : str):\n    return s[0].title() + s[2:] if s else s',
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


def test_mutate_dict():
    source = 'dict(a=b, c=d)'

    mutants = mutants_for_source(source)

    expected = [
        'dict(a=None, c=d)',
        'dict(aXX=b, c=d)',
        'dict(a=b, c=None)',
        'dict(a=b, cXX=d)',
        'dict(c=d)',
        'dict(a=b, )',
    ]

    assert sorted(mutants) == sorted(expected)


def test_syntax_error():
    with pytest.raises(cst.ParserSyntaxError):
        mutate_file_contents('some_file.py', ':!')


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
    assert mutants_for_source('') == []


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
    assert orig_function_and_class_names_from_key(f'_{CLASS_NAME_SEPARATOR}Foo{CLASS_NAME_SEPARATOR}bar__mutmut_1') == ('bar', 'Foo')
    assert orig_function_and_class_names_from_key('x_bar__mutmut_1') == ('bar', None)


def test_mangle_function_name():
    assert mangle_function_name(name='bar', class_name=None) == 'x_bar'
    assert mangle_function_name(name='bar', class_name='Foo') == f'x{CLASS_NAME_SEPARATOR}Foo{CLASS_NAME_SEPARATOR}bar'


def test_diff_ops():
    source = """
def foo():    
    return 1


class Foo:
    def member(self):        
        return 3

    """.strip()

    mutants_source, mutant_names = mutate_file_contents('filename', source)
    assert len(mutant_names) == 2

    diff1 = get_diff_for_mutant(mutant_name=mutant_names[0], source=mutants_source, path='test.py').strip()
    diff2 = get_diff_for_mutant(mutant_name=mutant_names[1], source=mutants_source, path='test.py').strip()

    assert diff1 == '''
--- test.py
+++ test.py
@@ -1,2 +1,2 @@
 def foo():    
-    return 1
+    return 2
'''.strip()

    assert diff2 == '''
--- test.py
+++ test.py
@@ -1,2 +1,2 @@
 def member(self):        
-    return 3
+    return 4
'''.strip()


def test_from_future_still_first():
    source = """
from __future__ import annotations
from collections.abc import Iterable

def foo():
    return 1
""".strip()
    mutated_source = mutated_module(source)
    assert mutated_source.split('\n')[0] == 'from __future__ import annotations'
    assert mutated_source.count('from __future__') == 1

def test_from_future_with_docstring_still_first():
    source = """
'''This documents the module'''
from __future__ import annotations
from collections.abc import Iterable

def foo():
    return 1
""".strip()
    mutated_source = mutated_module(source)
    assert mutated_source.split('\n')[0] == "'''This documents the module'''"
    assert mutated_source.split('\n')[1] == 'from __future__ import annotations'
    assert mutated_source.count('from __future__') == 1


# Negate the effects of CatchOutput because it does not play nicely with capfd in GitHub Actions
@patch.object(CatchOutput, 'dump_output')
@patch.object(CatchOutput, 'stop')
@patch.object(CatchOutput, 'start')
def test_run_forced_fail_test_with_failing_test(_start, _stop, _dump_output, capfd):
    mutmut._reset_globals()
    runner = _mocked_runner_run_forced_failed(return_value=1)

    run_forced_fail_test(runner)

    out, err = capfd.readouterr()

    print()
    print(f"out: {out}")
    print(f"err: {err}")
    assert 'done' in out
    assert os.environ['MUTANT_UNDER_TEST'] is ''


# Negate the effects of CatchOutput because it does not play nicely with capfd in GitHub Actions
@patch.object(CatchOutput, 'dump_output')
@patch.object(CatchOutput, 'stop')
@patch.object(CatchOutput, 'start')
def test_run_forced_fail_test_with_mutmut_programmatic_fail_exception(_start, _stop, _dump_output, capfd):
    mutmut._reset_globals()
    runner = _mocked_runner_run_forced_failed(side_effect=MutmutProgrammaticFailException())

    run_forced_fail_test(runner)

    out, err = capfd.readouterr()
    assert 'done' in out
    assert os.environ['MUTANT_UNDER_TEST'] is ''


# Negate the effects of CatchOutput because it does not play nicely with capfd in GitHub Actions
@patch.object(CatchOutput, 'dump_output')
@patch.object(CatchOutput, 'stop')
@patch.object(CatchOutput, 'start')
def test_run_forced_fail_test_with_all_tests_passing(_start, _stop, _dump_output, capfd):
    mutmut._reset_globals()
    runner = _mocked_runner_run_forced_failed(return_value=0)

    with pytest.raises(SystemExit) as error:
        run_forced_fail_test(runner)

    assert error.value.code is 1
    out, err = capfd.readouterr()
    assert 'FAILED: Unable to force test failures' in out


def _mocked_runner_run_forced_failed(return_value=None, side_effect=None):
    runner = Mock()
    runner.run_forced_fail = Mock(
        return_value=return_value,
        side_effect=side_effect
    )
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

# TODO: implement removal of inner decorators
@pytest.mark.skip
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


def test_module_mutation():
    source = """from __future__ import division
import lib

lib.foo()

def foo(a, b):
    return a > b

def bar():
    yield 1

class Adder:
    def __init__(self, amount):
        self.amount = amount

    def add(self, value):
        return self.amount + value

print(Adder(1).add(2))"""

    src, _ = mutate_file_contents("file.py", source)

    assert src == f"""from __future__ import division
import lib

lib.foo()
{trampoline_impl.strip()}

def x_foo__mutmut_orig(a, b):
    return a > b

def x_foo__mutmut_1(a, b):
    return a >= b

x_foo__mutmut_mutants : ClassVar[MutantDict] = {{
'x_foo__mutmut_1': x_foo__mutmut_1
}}

def foo(*args, **kwargs):
    result = _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs)
    return result 

foo.__signature__ = _mutmut_signature(x_foo__mutmut_orig)
x_foo__mutmut_orig.__name__ = 'x_foo'

def x_bar__mutmut_orig():
    yield 1

def x_bar__mutmut_1():
    yield 2

x_bar__mutmut_mutants : ClassVar[MutantDict] = {{
'x_bar__mutmut_1': x_bar__mutmut_1
}}

def bar(*args, **kwargs):
    result = _mutmut_trampoline(x_bar__mutmut_orig, x_bar__mutmut_mutants, args, kwargs)
    return result 

bar.__signature__ = _mutmut_signature(x_bar__mutmut_orig)
x_bar__mutmut_orig.__name__ = 'x_bar'

class Adder:
    def xǁAdderǁ__init____mutmut_orig(self, amount):
        self.amount = amount
    def xǁAdderǁ__init____mutmut_1(self, amount):
        self.amount = None
    
    xǁAdderǁ__init____mutmut_mutants : ClassVar[MutantDict] = {{
    'xǁAdderǁ__init____mutmut_1': xǁAdderǁ__init____mutmut_1
    }}
    
    def __init__(self, *args, **kwargs):
        result = _mutmut_trampoline(object.__getattribute__(self, "xǁAdderǁ__init____mutmut_orig"), object.__getattribute__(self, "xǁAdderǁ__init____mutmut_mutants"), args, kwargs, self)
        return result 
    
    __init__.__signature__ = _mutmut_signature(xǁAdderǁ__init____mutmut_orig)
    xǁAdderǁ__init____mutmut_orig.__name__ = 'xǁAdderǁ__init__'

    def xǁAdderǁadd__mutmut_orig(self, value):
        return self.amount + value

    def xǁAdderǁadd__mutmut_1(self, value):
        return self.amount - value
    
    xǁAdderǁadd__mutmut_mutants : ClassVar[MutantDict] = {{
    'xǁAdderǁadd__mutmut_1': xǁAdderǁadd__mutmut_1
    }}
    
    def add(self, *args, **kwargs):
        result = _mutmut_trampoline(object.__getattribute__(self, "xǁAdderǁadd__mutmut_orig"), object.__getattribute__(self, "xǁAdderǁadd__mutmut_mutants"), args, kwargs, self)
        return result 
    
    add.__signature__ = _mutmut_signature(xǁAdderǁadd__mutmut_orig)
    xǁAdderǁadd__mutmut_orig.__name__ = 'xǁAdderǁadd'

print(Adder(1).add(2))"""
