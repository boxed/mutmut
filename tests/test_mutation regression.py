import libcst as cst
from inline_snapshot import snapshot

from mutmut.mutation.file_mutation import create_trampoline_wrapper
from mutmut.mutation.file_mutation import mutate_file_contents


def _get_trampoline_wrapper(source: str, mangled_name: str, class_name: str | None = None) -> str:
    function = cst.ensure_type(cst.parse_statement(source), cst.FunctionDef)
    trampoline = create_trampoline_wrapper(function, mangled_name, class_name=class_name)
    return cst.Module([trampoline]).code.strip()


def test_create_trampoline_wrapper_async_method():
    source = "async def foo(a: str, b, *args, **kwargs) -> dict[str, int]: pass"

    assert _get_trampoline_wrapper(source, "x_foo__mutmut") == snapshot("""\
async def foo(a: str, b, *args, **kwargs) -> dict[str, int]:
    args = [a, b, *args]# type: ignore
    kwargs = {**kwargs}# type: ignore
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
    args = []# type: ignore
    kwargs = {}# type: ignore
    async for i in _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs, None):
        yield i\
""")


def test_create_trampoline_wrapper_with_positionals_only_args():
    source = "def foo(p1, p2=None, /, p_or_kw=None, *, kw): pass"

    assert _get_trampoline_wrapper(source, "x_foo__mutmut") == snapshot("""\
def foo(p1, p2=None, /, p_or_kw=None, *, kw):
    args = [p1, p2, p_or_kw]# type: ignore
    kwargs = {'kw': kw}# type: ignore
    return _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs, None)\
""")


def test_create_trampoline_wrapper_for_class_method():
    source = "def foo(self, a, b): pass"

    assert _get_trampoline_wrapper(source, "x_foo__mutmut", class_name="Person") == snapshot("""\
def foo(self, a, b):
    args = [a, b]# type: ignore
    kwargs = {}# type: ignore
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
from inspect import signature as _mutmut_signature # mutmut: generated
from typing import Annotated # mutmut: generated
from typing import Callable # mutmut: generated
from typing import ClassVar # mutmut: generated


MutantDict = Annotated[dict[str, Callable], "Mutant"] # type: ignore # mutmut: generated


def _mutmut_trampoline(orig, mutants, call_args, call_kwargs, self_arg = None): # type: ignore # mutmut: generated
    """Forward call to original or mutated function, depending on the environment""" # mutmut: generated
    import os # type: ignore # mutmut: generated
    mutant_under_test = os.environ.get('MUTANT_UNDER_TEST', '') # type: ignore # mutmut: generated
    if not mutant_under_test: # mutmut: generated
        # No mutant being tested - call original function
        if self_arg is not None and not hasattr(orig, '__self__'): # mutmut: generated
            return orig(self_arg, *call_args, **call_kwargs) # mutmut: generated
        else: # mutmut: generated
            return orig(*call_args, **call_kwargs) # mutmut: generated
    if mutant_under_test == 'fail': # type: ignore # mutmut: generated
        from mutmut.__main__ import MutmutProgrammaticFailException # type: ignore # mutmut: generated
        raise MutmutProgrammaticFailException('Failed programmatically')       # type: ignore # mutmut: generated
    elif mutant_under_test == 'stats': # type: ignore # mutmut: generated
        from mutmut.__main__ import record_trampoline_hit # type: ignore # mutmut: generated
        record_trampoline_hit(orig.__module__ + '.' + orig.__name__) # type: ignore # mutmut: generated
        # Check if orig is a bound method (has __self__) or plain function
        if self_arg is not None and not hasattr(orig, '__self__'): # type: ignore # mutmut: generated
            result = orig(self_arg, *call_args, **call_kwargs) # type: ignore # mutmut: generated
        else: # mutmut: generated
            result = orig(*call_args, **call_kwargs) # type: ignore # mutmut: generated
        return result # type: ignore # mutmut: generated
    prefix = orig.__module__ + '.' + orig.__name__ + '__mutmut_' # type: ignore # mutmut: generated
    if not mutant_under_test.startswith(prefix): # type: ignore # mutmut: generated
        # Check if orig is a bound method (has __self__) or plain function
        if self_arg is not None and not hasattr(orig, '__self__'): # type: ignore # mutmut: generated
            result = orig(self_arg, *call_args, **call_kwargs) # type: ignore # mutmut: generated
        else: # mutmut: generated
            result = orig(*call_args, **call_kwargs) # type: ignore # mutmut: generated
        return result # type: ignore # mutmut: generated
    mutant_name = mutant_under_test.rpartition('.')[-1] # type: ignore # mutmut: generated
    if self_arg is not None: # type: ignore # mutmut: generated
        # call to a class method where self is not bound
        result = mutants[mutant_name](self_arg, *call_args, **call_kwargs) # type: ignore # mutmut: generated
    else: # mutmut: generated
        result = mutants[mutant_name](*call_args, **call_kwargs) # type: ignore # mutmut: generated
    return result # type: ignore # mutmut: generated

def foo(a: list[int], b):
    args = [a, b]# type: ignore
    kwargs = {}# type: ignore
    return _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs, None)

def x_foo__mutmut_orig(a: list[int], b):
    return a[0] > b

def x_foo__mutmut_1(a: list[int], b):
    return a[1] > b

def x_foo__mutmut_2(a: list[int], b):
    return a[0] >= b

x_foo__mutmut_mutants : MutantDict = { # mutmut: generated
'x_foo__mutmut_1': x_foo__mutmut_1,  # mutmut: generated
    'x_foo__mutmut_2': x_foo__mutmut_2 # mutmut: generated
} # mutmut: generated

def foo(*args, **kwargs): # mutmut: generated
    result = _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs) # mutmut: generated
    return result # mutmut: generated

foo.__signature__ = _mutmut_signature(x_foo__mutmut_orig) # mutmut: generated
foo.__annotations__ = x_foo__mutmut_orig.__annotations__ # mutmut: generated
x_foo__mutmut_orig.__name__ = 'x_foo' # mutmut: generated

def bar():
    args = []# type: ignore
    kwargs = {}# type: ignore
    return _mutmut_trampoline(x_bar__mutmut_orig, x_bar__mutmut_mutants, args, kwargs, None)

def x_bar__mutmut_orig():
    yield 1

def x_bar__mutmut_1():
    yield 2

x_bar__mutmut_mutants : MutantDict = { # mutmut: generated
'x_bar__mutmut_1': x_bar__mutmut_1 # mutmut: generated
} # mutmut: generated

def bar(*args, **kwargs): # mutmut: generated
    result = _mutmut_trampoline(x_bar__mutmut_orig, x_bar__mutmut_mutants, args, kwargs) # mutmut: generated
    return result # mutmut: generated

bar.__signature__ = _mutmut_signature(x_bar__mutmut_orig) # mutmut: generated
bar.__annotations__ = x_bar__mutmut_orig.__annotations__ # mutmut: generated
x_bar__mutmut_orig.__name__ = 'x_bar' # mutmut: generated

class Adder:
    def __init__(self, amount):
        args = [amount]# type: ignore
        kwargs = {}# type: ignore
        return _mutmut_trampoline(object.__getattribute__(self, 'xǁAdderǁ__init____mutmut_orig'), object.__getattribute__(self, 'xǁAdderǁ__init____mutmut_mutants'), args, kwargs, self)
    def xǁAdderǁ__init____mutmut_orig(self, amount):
        self.amount = amount
    def xǁAdderǁ__init____mutmut_1(self, amount):
        self.amount = None
    \n\
    xǁAdderǁ__init____mutmut_mutants : ClassVar[MutantDict] = { # mutmut: generated
    'xǁAdderǁ__init____mutmut_1': xǁAdderǁ__init____mutmut_1 # mutmut: generated
    } # mutmut: generated
    \n\
    def __init__(self, *args, **kwargs): # mutmut: generated
        result = _mutmut_trampoline(object.__getattribute__(self, "xǁAdderǁ__init____mutmut_orig"), object.__getattribute__(self, "xǁAdderǁ__init____mutmut_mutants"), args, kwargs, self) # mutmut: generated
        return result # mutmut: generated
    \n\
    __init__.__signature__ = _mutmut_signature(xǁAdderǁ__init____mutmut_orig) # mutmut: generated
    __init__.__annotations__ = xǁAdderǁ__init____mutmut_orig.__annotations__ # mutmut: generated
    xǁAdderǁ__init____mutmut_orig.__name__ = 'xǁAdderǁ__init__' # mutmut: generated

    def add(self, value):
        args = [value]# type: ignore
        kwargs = {}# type: ignore
        return _mutmut_trampoline(object.__getattribute__(self, 'xǁAdderǁadd__mutmut_orig'), object.__getattribute__(self, 'xǁAdderǁadd__mutmut_mutants'), args, kwargs, self)

    def xǁAdderǁadd__mutmut_orig(self, value):
        return self.amount + value

    def xǁAdderǁadd__mutmut_1(self, value):
        return self.amount - value
    \n\
    xǁAdderǁadd__mutmut_mutants : ClassVar[MutantDict] = { # mutmut: generated
    'xǁAdderǁadd__mutmut_1': xǁAdderǁadd__mutmut_1 # mutmut: generated
    } # mutmut: generated
    \n\
    def add(self, *args, **kwargs): # mutmut: generated
        result = _mutmut_trampoline(object.__getattribute__(self, "xǁAdderǁadd__mutmut_orig"), object.__getattribute__(self, "xǁAdderǁadd__mutmut_mutants"), args, kwargs, self) # mutmut: generated
        return result # mutmut: generated
    \n\
    add.__signature__ = _mutmut_signature(xǁAdderǁadd__mutmut_orig) # mutmut: generated
    add.__annotations__ = xǁAdderǁadd__mutmut_orig.__annotations__ # mutmut: generated
    xǁAdderǁadd__mutmut_orig.__name__ = 'xǁAdderǁadd' # mutmut: generated

print(Adder(1).add(2))\
''')
