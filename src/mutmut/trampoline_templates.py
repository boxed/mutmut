CLASS_NAME_SEPARATOR = 'ǁ'

def build_trampoline(*, orig_name, mutants, class_name):
    mangled_name = mangle_function_name(name=orig_name, class_name=class_name)

    mutants_dict = f'{mangled_name}__mutmut_mutants : ClassVar[MutantDict] = {{ # type: ignore\n' + ', \n    '.join(f'{repr(m)}: {m}' for m in mutants) + '\n}'
    access_prefix = ''
    access_suffix = ''
    self_arg = ''
    if class_name is not None:
        access_prefix = f'object.__getattribute__(self, "'
        access_suffix = '")'
        self_arg = ', self'

    trampoline_name = '_mutmut_trampoline'

    return f"""
{mutants_dict}

def {orig_name}({'self, ' if class_name is not None else ''}*args, **kwargs):
    result = {trampoline_name}({access_prefix}{mangled_name}__mutmut_orig{access_suffix}, {access_prefix}{mangled_name}__mutmut_mutants{access_suffix}, args, kwargs{self_arg})
    return result 

_mutmut_copy_signature({orig_name}, {mangled_name}__mutmut_orig)
{mangled_name}__mutmut_orig.__name__ = '{mangled_name}'
"""

def mangle_function_name(*, name, class_name):
    assert CLASS_NAME_SEPARATOR not in name
    if class_name:
        assert CLASS_NAME_SEPARATOR not in class_name
        prefix = f'x{CLASS_NAME_SEPARATOR}{class_name}{CLASS_NAME_SEPARATOR}'
    else:
        prefix = 'x_'
    return f'{prefix}{name}'

# noinspection PyUnresolvedReferences
# language=python
trampoline_impl = """
import inspect as _mutmut_inspect
import sys as _mutmut_sys
from typing import Annotated
from typing import Callable
from typing import ClassVar

def _mutmut_copy_signature(trampoline, original_method):
    if _mutmut_sys.version_info >= (3, 14):
        # PEP 649 introduced deferred loading for annotations
        # When some_method.__annotations__ is accessed, Python uses some_method.__annotate__(format) to compute it
        # By copying the original __annotate__ method, we provide get the original annotations
        trampoline.__annotate__ = original_method.__annotate__
    else:
        # On Python 3.13 and earlier, __annotations__ can be accessed immediately
        trampoline.__annotations__ = original_method.__annotations__

    try:
        trampoline.__signature__ = _mutmut_inspect.signature(original_method)
    except NameError:
        # Also, because of PEP 649, it can happen that we cannot eagerly evaluate the signature
        # In this case, fall back to stringifying the signature (which could cause different behaviour with runtime introspection)
        trampoline.__signature__ = _mutmut_inspect.signature(original_method, annotation_format=_mutmut_inspect.Format.STRING)  # type: ignore



MutantDict = Annotated[dict[str, Callable], "Mutant"]


def _mutmut_trampoline(orig, mutants, call_args, call_kwargs, self_arg = None):
    \"""Forward call to original or mutated function, depending on the environment\"""
    import os
    mutant_under_test = os.environ['MUTANT_UNDER_TEST']
    if mutant_under_test == 'fail':
        from mutmut.__main__ import MutmutProgrammaticFailException
        raise MutmutProgrammaticFailException('Failed programmatically')      
    elif mutant_under_test == 'stats':
        from mutmut.__main__ import record_trampoline_hit
        record_trampoline_hit(orig.__module__ + '.' + orig.__name__)
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

"""
