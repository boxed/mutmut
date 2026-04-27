import re

from inline_snapshot import snapshot

from mutmut.mutation.file_mutation import mutate_file_contents


def mutated_module(source: str) -> str:
    mutated_code, _, _, _ = mutate_file_contents("test.py", source)
    return mutated_code


def test_mutate_file_contents():
    source = """
a + 1

def foo(a, b, c):
    return a + b * c
"""

    result = mutated_module(source)

    assert result == snapshot('''\

a + 1
import os # type: ignore # mutmut generated
from collections.abc import Sequence # type: ignore # mutmut generated
from typing import Annotated # type: ignore # mutmut generated
from typing import Callable # type: ignore # mutmut generated
from typing import ClassVar # type: ignore # mutmut generated
from typing import TypeVar # type: ignore # mutmut generated
from mutmut.core import MutmutProgrammaticFailException # type: ignore # mutmut generated
from mutmut.core import record_trampoline_hit # type: ignore # mutmut generated
from mutmut.core import MutmutCallStack # type: ignore # mutmut generated

TReturn = TypeVar('TReturn') # type: ignore # mutmut generated
MutantDict = Annotated[dict[str, Callable[..., TReturn]], "Mutant"] # type: ignore # mutmut generated


def _mutmut_trampoline(orig: Callable[..., TReturn], mutants: MutantDict, call_args: Sequence, call_kwargs: dict, self_arg = None) -> TReturn: # type: ignore # mutmut generated
    """Forward call to original or mutated function, depending on the environment""" # type: ignore # mutmut generated
    mutant_under_test = os.environ.get('MUTANT_UNDER_TEST', '') # type: ignore # mutmut generated
    if not mutant_under_test: # type: ignore # mutmut generated
        # No mutant being tested - call original function
        if self_arg is not None and not hasattr(orig, '__self__'): # type: ignore # mutmut generated
            return orig(self_arg, *call_args, **call_kwargs) # type: ignore # mutmut generated
        else: # type: ignore # mutmut generated
            return orig(*call_args, **call_kwargs) # type: ignore # mutmut generated
    if mutant_under_test == 'fail': # type: ignore # mutmut generated
        raise MutmutProgrammaticFailException('Failed programmatically') # type: ignore # mutmut generated
    elif mutant_under_test == 'stats': # type: ignore # mutmut generated
        my_name = orig.__module__ + '.' + orig.__name__ # type: ignore # mutmut generated
        # Normalize module names - strip 'mutants.' prefix for consistency with test mappings
        if my_name.startswith('mutants.'): # type: ignore # mutmut generated
            my_name = my_name[8:]  # len('mutants.') == 8 # type: ignore # mutmut generated

        caller_name, depth = MutmutCallStack.get() # type: ignore # mutmut generated

        # Also normalize caller name
        if caller_name and caller_name.startswith('mutants.'): # type: ignore # mutmut generated
            caller_name = caller_name[8:] # type: ignore # mutmut generated

        max_depth = int(os.environ.get("MUTMUT_DEPENDENCY_DEPTH", "-1")) # type: ignore # mutmut generated

        if max_depth == -1 or depth < max_depth: # type: ignore # mutmut generated
            record_trampoline_hit(my_name, caller=caller_name) # type: ignore # mutmut generated

            token = MutmutCallStack.set((my_name, depth + 1)) # type: ignore # mutmut generated
            try: # type: ignore # mutmut generated
                if self_arg is not None and not hasattr(orig, "__self__"): # type: ignore # mutmut generated
                    result = orig(self_arg, *call_args, **call_kwargs) # type: ignore # mutmut generated
                else: # type: ignore # mutmut generated
                    result = orig(*call_args, **call_kwargs) # type: ignore # mutmut generated
                return result # type: ignore # mutmut generated
            finally: # type: ignore # mutmut generated
                MutmutCallStack.reset(token) # type: ignore # mutmut generated
        else: # type: ignore # mutmut generated
            # Depth exceeded — still call but don't track deeper
            if self_arg is not None and not hasattr(orig, "__self__"): # type: ignore # mutmut generated
                result = orig(self_arg, *call_args, **call_kwargs) # type: ignore # mutmut generated
            else: # type: ignore # mutmut generated
                result = orig(*call_args, **call_kwargs) # type: ignore # mutmut generated
            return result # type: ignore # mutmut generated
    prefix = orig.__module__ + '.' + orig.__name__ + '__mutmut_' # type: ignore # mutmut generated
    if not mutant_under_test.startswith(prefix): # type: ignore # mutmut generated
        # Check if orig is a bound method (has __self__) or plain function
        if self_arg is not None and not hasattr(orig, '__self__'): # type: ignore # mutmut generated
            result = orig(self_arg, *call_args, **call_kwargs) # type: ignore # mutmut generated
        else: # type: ignore # mutmut generated
            result = orig(*call_args, **call_kwargs) # type: ignore # mutmut generated
        return result # type: ignore # mutmut generated
    mutant_name = mutant_under_test.rpartition('.')[-1] # type: ignore # mutmut generated
    if self_arg is not None: # type: ignore # mutmut generated
        # call to a class method where self is not bound
        result = mutants[mutant_name](self_arg, *call_args, **call_kwargs) # type: ignore # mutmut generated
    else: # type: ignore # mutmut generated
        result = mutants[mutant_name](*call_args, **call_kwargs) # type: ignore # mutmut generated
    return result # type: ignore # mutmut generated

def foo(a, b, c):
    args = [a, b, c]# type: ignore
    kwargs = {}# type: ignore
    return _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs, None)# type: ignore

def x_foo__mutmut_orig(a, b, c):
    return a + b * c

def x_foo__mutmut_1(a, b, c):
    return a - b * c

def x_foo__mutmut_2(a, b, c):
    return a + b / c

x_foo__mutmut_mutants : MutantDict = { # type: ignore # mutmut generated
    'x_foo__mutmut_1': x_foo__mutmut_1, # type: ignore # mutmut generated
    'x_foo__mutmut_2': x_foo__mutmut_2 # type: ignore # mutmut generated
} # type: ignore # mutmut generated

x_foo__mutmut_orig.__name__ = 'x_foo' # type: ignore # mutmut generated
''')


def test_avoid_annotations():
    source = """
def foo(a: List[int]) -> int:
    return 1
"""

    result = mutated_module(source)

    assert result == snapshot('''\

import os # type: ignore # mutmut generated
from collections.abc import Sequence # type: ignore # mutmut generated
from typing import Annotated # type: ignore # mutmut generated
from typing import Callable # type: ignore # mutmut generated
from typing import ClassVar # type: ignore # mutmut generated
from typing import TypeVar # type: ignore # mutmut generated
from mutmut.core import MutmutProgrammaticFailException # type: ignore # mutmut generated
from mutmut.core import record_trampoline_hit # type: ignore # mutmut generated
from mutmut.core import MutmutCallStack # type: ignore # mutmut generated

TReturn = TypeVar('TReturn') # type: ignore # mutmut generated
MutantDict = Annotated[dict[str, Callable[..., TReturn]], "Mutant"] # type: ignore # mutmut generated


def _mutmut_trampoline(orig: Callable[..., TReturn], mutants: MutantDict, call_args: Sequence, call_kwargs: dict, self_arg = None) -> TReturn: # type: ignore # mutmut generated
    """Forward call to original or mutated function, depending on the environment""" # type: ignore # mutmut generated
    mutant_under_test = os.environ.get('MUTANT_UNDER_TEST', '') # type: ignore # mutmut generated
    if not mutant_under_test: # type: ignore # mutmut generated
        # No mutant being tested - call original function
        if self_arg is not None and not hasattr(orig, '__self__'): # type: ignore # mutmut generated
            return orig(self_arg, *call_args, **call_kwargs) # type: ignore # mutmut generated
        else: # type: ignore # mutmut generated
            return orig(*call_args, **call_kwargs) # type: ignore # mutmut generated
    if mutant_under_test == 'fail': # type: ignore # mutmut generated
        raise MutmutProgrammaticFailException('Failed programmatically') # type: ignore # mutmut generated
    elif mutant_under_test == 'stats': # type: ignore # mutmut generated
        my_name = orig.__module__ + '.' + orig.__name__ # type: ignore # mutmut generated
        # Normalize module names - strip 'mutants.' prefix for consistency with test mappings
        if my_name.startswith('mutants.'): # type: ignore # mutmut generated
            my_name = my_name[8:]  # len('mutants.') == 8 # type: ignore # mutmut generated

        caller_name, depth = MutmutCallStack.get() # type: ignore # mutmut generated

        # Also normalize caller name
        if caller_name and caller_name.startswith('mutants.'): # type: ignore # mutmut generated
            caller_name = caller_name[8:] # type: ignore # mutmut generated

        max_depth = int(os.environ.get("MUTMUT_DEPENDENCY_DEPTH", "-1")) # type: ignore # mutmut generated

        if max_depth == -1 or depth < max_depth: # type: ignore # mutmut generated
            record_trampoline_hit(my_name, caller=caller_name) # type: ignore # mutmut generated

            token = MutmutCallStack.set((my_name, depth + 1)) # type: ignore # mutmut generated
            try: # type: ignore # mutmut generated
                if self_arg is not None and not hasattr(orig, "__self__"): # type: ignore # mutmut generated
                    result = orig(self_arg, *call_args, **call_kwargs) # type: ignore # mutmut generated
                else: # type: ignore # mutmut generated
                    result = orig(*call_args, **call_kwargs) # type: ignore # mutmut generated
                return result # type: ignore # mutmut generated
            finally: # type: ignore # mutmut generated
                MutmutCallStack.reset(token) # type: ignore # mutmut generated
        else: # type: ignore # mutmut generated
            # Depth exceeded — still call but don't track deeper
            if self_arg is not None and not hasattr(orig, "__self__"): # type: ignore # mutmut generated
                result = orig(self_arg, *call_args, **call_kwargs) # type: ignore # mutmut generated
            else: # type: ignore # mutmut generated
                result = orig(*call_args, **call_kwargs) # type: ignore # mutmut generated
            return result # type: ignore # mutmut generated
    prefix = orig.__module__ + '.' + orig.__name__ + '__mutmut_' # type: ignore # mutmut generated
    if not mutant_under_test.startswith(prefix): # type: ignore # mutmut generated
        # Check if orig is a bound method (has __self__) or plain function
        if self_arg is not None and not hasattr(orig, '__self__'): # type: ignore # mutmut generated
            result = orig(self_arg, *call_args, **call_kwargs) # type: ignore # mutmut generated
        else: # type: ignore # mutmut generated
            result = orig(*call_args, **call_kwargs) # type: ignore # mutmut generated
        return result # type: ignore # mutmut generated
    mutant_name = mutant_under_test.rpartition('.')[-1] # type: ignore # mutmut generated
    if self_arg is not None: # type: ignore # mutmut generated
        # call to a class method where self is not bound
        result = mutants[mutant_name](self_arg, *call_args, **call_kwargs) # type: ignore # mutmut generated
    else: # type: ignore # mutmut generated
        result = mutants[mutant_name](*call_args, **call_kwargs) # type: ignore # mutmut generated
    return result # type: ignore # mutmut generated
def foo(a: List[int]) -> int:
    args = [a]# type: ignore
    kwargs = {}# type: ignore
    return _mutmut_trampoline(x_foo__mutmut_orig, x_foo__mutmut_mutants, args, kwargs, None)# type: ignore
def x_foo__mutmut_orig(a: List[int]) -> int:
    return 1
def x_foo__mutmut_1(a: List[int]) -> int:
    return 2

x_foo__mutmut_mutants : MutantDict = { # type: ignore # mutmut generated
    'x_foo__mutmut_1': x_foo__mutmut_1 # type: ignore # mutmut generated
} # type: ignore # mutmut generated

x_foo__mutmut_orig.__name__ = 'x_foo' # type: ignore # mutmut generated
''')


def test_staticmethod_trampoline_has_no_self_parameter():
    """Regression test: staticmethod trampolines must not have 'self' parameter.

    When a @staticmethod is mutated, the generated trampoline function should
    NOT have 'self' as its first parameter. If it does, calling the method
    will fail with: TypeError: missing 1 required positional argument: 'self'
    """
    source = """
class MyService:
    @staticmethod
    def process(value: int) -> int:
        return value + 1
"""
    result = mutated_module(source)

    # Find the trampoline function definition
    # It should be: def xǁMyServiceǁprocess__mutmut_trampoline(*args, **kwargs):
    # NOT:          def xǁMyServiceǁprocess__mutmut_trampoline(self, *args, **kwargs):
    trampoline_match = re.search(r"def xǁMyServiceǁprocess__mutmut_trampoline\(([^)]*)\):", result)
    assert trampoline_match is not None, "Trampoline function not found in output"

    params = trampoline_match.group(1)
    assert "self" not in params, f"staticmethod trampoline should not have 'self' parameter, got: ({params})"
    assert params == "*args, **kwargs", f"staticmethod trampoline should have (*args, **kwargs), got: ({params})"

    # Also verify the class uses staticmethod() wrapper
    assert "process = staticmethod(xǁMyServiceǁprocess__mutmut_trampoline)" in result, (
        "Class should wrap trampoline with staticmethod()"
    )


def test_classmethod_trampoline_has_cls_parameter():
    """Verify classmethod trampolines have 'cls' as first parameter."""
    source = """
class MyService:
    @classmethod
    def create(cls, value: int) -> int:
        return value + 1
"""
    result = mutated_module(source)

    # Find the trampoline function definition
    # It should be: def xǁMyServiceǁcreate__mutmut_trampoline(cls, *args, **kwargs):
    trampoline_match = re.search(r"def xǁMyServiceǁcreate__mutmut_trampoline\(([^)]*)\):", result)
    assert trampoline_match is not None, "Trampoline function not found in output"

    params = trampoline_match.group(1)
    assert params == "cls, *args, **kwargs", (
        f"classmethod trampoline should have (cls, *args, **kwargs), got: ({params})"
    )

    # Also verify the class uses classmethod() wrapper
    assert "create = classmethod(xǁMyServiceǁcreate__mutmut_trampoline)" in result, (
        "Class should wrap trampoline with classmethod()"
    )
