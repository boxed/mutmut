CLASS_NAME_SEPARATOR = 'ǁ'

def create_trampoline_lookup(*, orig_name, mutants, class_name):
    mangled_name = mangle_function_name(name=orig_name, class_name=class_name)

    mutants_dict = f'{mangled_name}__mutmut_mutants : ClassVar[MutantDict] = {{ # type: ignore\n' + ', \n    '.join(f'{repr(m)}: {m}' for m in mutants) + '\n}'
    return f"""
{mutants_dict}
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
from typing import Annotated
from typing import Callable
from typing import ClassVar

MutantDict = Annotated[dict[str, Callable], "Mutant"] # type: ignore


def _mutmut_trampoline(orig, mutants, call_args, call_kwargs, self_arg = None): # type: ignore
    \"""Forward call to original or mutated function, depending on the environment\"""
    import os # type: ignore
    mutant_under_test = os.environ['MUTANT_UNDER_TEST'] # type: ignore
    if mutant_under_test == 'fail': # type: ignore
        from mutmut.__main__ import MutmutProgrammaticFailException # type: ignore
        raise MutmutProgrammaticFailException('Failed programmatically')       # type: ignore
    elif mutant_under_test == 'stats': # type: ignore
        from mutmut.__main__ import record_trampoline_hit # type: ignore
        record_trampoline_hit(orig.__module__ + '.' + orig.__name__) # type: ignore
        # (for class methods, orig is bound and thus does not need the explicit self argument)
        result = orig(*call_args, **call_kwargs) # type: ignore
        return result # type: ignore
    prefix = orig.__module__ + '.' + orig.__name__ + '__mutmut_' # type: ignore
    if not mutant_under_test.startswith(prefix): # type: ignore
        result = orig(*call_args, **call_kwargs) # type: ignore
        return result # type: ignore
    mutant_name = mutant_under_test.rpartition('.')[-1] # type: ignore
    if self_arg is not None: # type: ignore
        # call to a class method where self is not bound
        result = mutants[mutant_name](self_arg, *call_args, **call_kwargs) # type: ignore
    else:
        result = mutants[mutant_name](*call_args, **call_kwargs) # type: ignore
    return result # type: ignore

"""
