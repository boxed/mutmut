from inline_snapshot import snapshot
import libcst as cst

from mutmut.file_mutation import mutate_file_contents, create_trampoline_wrapper


def _get_trampoline_wrapper(
    source: str, mangled_name: str, class_name: str | None = None
) -> str:
    function = cst.ensure_type(cst.parse_statement(source), cst.FunctionDef)
    trampoline = create_trampoline_wrapper(
        function, mangled_name, class_name=class_name
    )
    return cst.Module([trampoline]).code.strip()


def test_create_trampoline_wrapper_async_method():
    source = "async def foo(a: str, b, *args, **kwargs) -> dict[str, int]: pass"

    assert _get_trampoline_wrapper(source, "x_foo__mutmut") == snapshot("""\
async def foo(a: str, b, *args, **kwargs) -> dict[str, int]:
    args = [a, b, *args]
    kwargs = {**kwargs}
    return await _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs, None)\
""")


def test_create_trampoline_wrapper_async_generator():
    source = """
async def foo():
    for i in range(10):
        yield i
    """

    assert _get_trampoline_wrapper(source, "x_foo__mutmut") == snapshot("""\
async def foo():
    args = []
    kwargs = {}
    async for i in _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs, None):
        yield i\
""")


def test_create_trampoline_wrapper_with_positionals_only_args():
    source = "def foo(p1, p2=None, /, p_or_kw=None, *, kw): pass"

    assert _get_trampoline_wrapper(source, "x_foo__mutmut") == snapshot("""\
def foo(p1, p2=None, /, p_or_kw=None, *, kw):
    args = [p1, p2, p_or_kw]
    kwargs = {'kw': kw}
    return _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs, None)\
""")


def test_create_trampoline_wrapper_for_class_method():
    source = "def foo(self, a, b): pass"

    assert _get_trampoline_wrapper(
        source, "x_foo__mutmut", class_name="Person"
    ) == snapshot("""\
def foo(self, a, b):
    args = [a, b]
    kwargs = {}
    return _mutmut_trampoline(object.__getattribute__(self, 'x_foo__mutmut_orig'), object.__getattribute__(self, 'x_foo__mutmut_mutants'), args, kwargs, self)\
""")


def test_module_mutation():
    """Regression test, for a complete module with functions, type annotations and a class"""

    source = """from __future__ import division
import lib

lib.foo()

def foo(a: list[int], b):
    return a[0] > b

def bar():
    yield 1

class Adder:
    def __init__(self, amount):
        self.amount = amount

    def add(self, value):
        return self.amount + value

print(Adder(1).add(2))"""

    src, _ = mutate_file_contents("file.py", source)

    assert src == snapshot('''\
from __future__ import division
import lib

lib.foo()
from typing import Annotated
from typing import Callable
from typing import ClassVar

MutantDict = Annotated[dict[str, Callable], "Mutant"]


def _mutmut_trampoline(orig, mutants, call_args, call_kwargs, self_arg = None):
    """Forward call to original or mutated function, depending on the environment"""
    import os
    mutant_under_test = os.environ['MUTANT_UNDER_TEST']
    if mutant_under_test == 'fail':
        from mutmut.__main__ import MutmutProgrammaticFailException
        raise MutmutProgrammaticFailException('Failed programmatically')      \n\
    elif mutant_under_test == 'stats':
        from mutmut.__main__ import record_trampoline_hit
        record_trampoline_hit(orig.__module__ + '.' + orig.__name__)
        # (for class methods, orig is bound and thus does not need the explicit self argument)
        result = orig(*call_args, **call_kwargs)
        return result
    prefix = orig.__module__ + '.' + orig.__name__ + '__mutmut_'
    if not mutant_under_test.startswith(prefix):
        result = orig(*call_args, **call_kwargs)
        return result
    mutant_name = mutant_under_test.rpartition('.')[-1]
    if self_arg is not None:
        # call to a class method where self is not bound
        result = mutants[mutant_name](self_arg, *call_args, **call_kwargs)
    else:
        result = mutants[mutant_name](*call_args, **call_kwargs)
    return result

def x_foo__mutmut_orig(a: list[int], b):
    return a[0] > b

def x_foo__mutmut_1(a: list[int], b):
    return a[1] > b

def x_foo__mutmut_2(a: list[int], b):
    return a[0] >= b

def foo(a: list[int], b):
    args = [a, b]
    kwargs = {}
    return _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs, None)

x_foo__mutmut_mutants : ClassVar[MutantDict] = {
'x_foo__mutmut_1': x_foo__mutmut_1, \n\
    'x_foo__mutmut_2': x_foo__mutmut_2
}
x_foo__mutmut_orig.__name__ = 'x_foo'

def x_bar__mutmut_orig():
    yield 1

def x_bar__mutmut_1():
    yield 2

def bar():
    args = []
    kwargs = {}
    return _mutmut_trampoline(x_bar__mutmut_orig, x_bar__mutmut_mutants, args, kwargs, None)

x_bar__mutmut_mutants : ClassVar[MutantDict] = {
'x_bar__mutmut_1': x_bar__mutmut_1
}
x_bar__mutmut_orig.__name__ = 'x_bar'

class Adder:
    def xǁAdderǁ__init____mutmut_orig(self, amount):
        self.amount = amount
    def xǁAdderǁ__init____mutmut_1(self, amount):
        self.amount = None
    def __init__(self, amount):
        args = [amount]
        kwargs = {}
        return _mutmut_trampoline(object.__getattribute__(self, 'xǁAdderǁ__init____mutmut_orig'), object.__getattribute__(self, 'xǁAdderǁ__init____mutmut_mutants'), args, kwargs, self)
    \n\
    xǁAdderǁ__init____mutmut_mutants : ClassVar[MutantDict] = {
    'xǁAdderǁ__init____mutmut_1': xǁAdderǁ__init____mutmut_1
    }
    xǁAdderǁ__init____mutmut_orig.__name__ = 'xǁAdderǁ__init__'

    def xǁAdderǁadd__mutmut_orig(self, value):
        return self.amount + value

    def xǁAdderǁadd__mutmut_1(self, value):
        return self.amount - value

    def add(self, value):
        args = [value]
        kwargs = {}
        return _mutmut_trampoline(object.__getattribute__(self, 'xǁAdderǁadd__mutmut_orig'), object.__getattribute__(self, 'xǁAdderǁadd__mutmut_mutants'), args, kwargs, self)
    \n\
    xǁAdderǁadd__mutmut_mutants : ClassVar[MutantDict] = {
    'xǁAdderǁadd__mutmut_1': xǁAdderǁadd__mutmut_1
    }
    xǁAdderǁadd__mutmut_orig.__name__ = 'xǁAdderǁadd'

print(Adder(1).add(2))\
''')
