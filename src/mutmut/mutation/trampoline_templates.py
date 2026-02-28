from mutmut.mutation.mutators import MethodType

CLASS_NAME_SEPARATOR = "ǁ"

GENERATED_MARKER = "# type: ignore # mutmut generated"


def _mark_generated(code: str) -> str:
    """Append the generated marker comment to every code line in a block."""
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            line = f"{line} {GENERATED_MARKER}"
        lines.append(line)
    return "\n".join(lines)


def mangle_function_name(*, name: str, class_name: str | None) -> str:
    assert CLASS_NAME_SEPARATOR not in name
    if class_name:
        assert CLASS_NAME_SEPARATOR not in class_name
        prefix = f"x{CLASS_NAME_SEPARATOR}{class_name}{CLASS_NAME_SEPARATOR}"
    else:
        prefix = "x_"
    return f"{prefix}{name}"


def build_mutants_dict_and_name(
    *,
    orig_name: str,
    mutants: list[str],
    class_name: str | None,
) -> str:
    """Generate the mutants dictionary and __name__ fix for a function trampoline.

    :param mutants: List of mutant function names (mangled)
    :param class_name: The containing class name, or None for top-level functions
    :param orig_name: The original function name
    :return: String containing the mutants dict and __name__ assignment
    """
    mangled_name = mangle_function_name(name=orig_name, class_name=class_name)

    type_annotation = "ClassVar[MutantDict]" if class_name is not None else "MutantDict"
    mutants_dict_entries = ",\n".join(f"    {repr(m)}: {m}" for m in mutants)
    mutants_dict = f"{mangled_name}__mutmut_mutants : {type_annotation} = {{\n{mutants_dict_entries}\n}}"

    return _mark_generated(f"""
{mutants_dict}

{mangled_name}__mutmut_orig.__name__ = '{mangled_name}'
""")


def build_enum_trampoline(
    *, class_name: str, method_name: str, mutant_names: list[str], method_type: MethodType
) -> str:
    """Generate external trampoline code for enum methods.

    This pattern moves all mutation-related code OUTSIDE the enum class body,
    avoiding the enum metaclass conflict. The enum class only contains a simple
    assignment like `method_name = _ClassName_method_trampoline`.

    :param class_name: The enum class name
    :param method_name: The method being mutated
    :param mutant_names: List of mutant function names (mangled)
    :param method_type: 'instance', 'static', or 'classmethod'
    :return: String containing the external functions and mutants dict
    """
    prefix = f"_{class_name}_{method_name}"
    mangled_name = mangle_function_name(name=method_name, class_name=class_name)

    # Build mutants dict
    mutants_dict_entries = ",\n".join(f"    {repr(m)}: {prefix}_mutant_{i + 1}" for i, m in enumerate(mutant_names))
    mutants_dict = f"{prefix}_mutants: MutantDict = {{\n{mutants_dict_entries}\n}}"

    orig_name_fix = f"{prefix}_orig.__name__ = '{mangled_name}'"

    # Build trampoline based on method type
    if method_type == MethodType.STATICMETHOD:
        trampoline = f"""

def {prefix}_trampoline(*args, **kwargs):
    return _mutmut_trampoline({prefix}_orig, {prefix}_mutants, args, kwargs)

{prefix}_trampoline.__name__ = '{method_name}'
"""
    elif method_type == MethodType.CLASSMETHOD:
        trampoline = f"""

def {prefix}_trampoline(cls, *args, **kwargs):
    return _mutmut_trampoline({prefix}_orig, {prefix}_mutants, args, kwargs, cls)

{prefix}_trampoline.__name__ = '{method_name}'
"""
    else:  # instance method
        trampoline = f"""

def {prefix}_trampoline(self, *args, **kwargs):
    return _mutmut_trampoline({prefix}_orig, {prefix}_mutants, args, kwargs, self)

{prefix}_trampoline.__name__ = '{method_name}'
"""

    return _mark_generated(f"\n\n{orig_name_fix}\n\n{mutants_dict}\n\n{trampoline}")


# noinspection PyUnresolvedReferences
# language=python
trampoline_impl = _mark_generated("""
from collections.abc import Sequence
from typing import Annotated
from typing import Callable
from typing import ClassVar
from typing import TypeVar

TReturn = TypeVar('TReturn')
MutantDict = Annotated[dict[str, Callable[..., TReturn]], "Mutant"]


def _mutmut_trampoline(orig: Callable[..., TReturn], mutants: MutantDict, call_args: Sequence, call_kwargs: dict, self_arg = None) -> TReturn:
    \"""Forward call to original or mutated function, depending on the environment\"""
    import os
    mutant_under_test = os.environ.get('MUTANT_UNDER_TEST', '')
    if not mutant_under_test:
        # No mutant being tested - call original function
        if self_arg is not None and not hasattr(orig, '__self__'):
            return orig(self_arg, *call_args, **call_kwargs)
        else:
            return orig(*call_args, **call_kwargs)
    if mutant_under_test == 'fail':
        from mutmut.__main__ import MutmutProgrammaticFailException
        raise MutmutProgrammaticFailException('Failed programmatically')
    elif mutant_under_test == 'stats':
        from mutmut.__main__ import record_trampoline_hit
        record_trampoline_hit(orig.__module__ + '.' + orig.__name__)
        # Check if orig is a bound method (has __self__) or plain function
        if self_arg is not None and not hasattr(orig, '__self__'):
            result = orig(self_arg, *call_args, **call_kwargs)
        else:
            result = orig(*call_args, **call_kwargs)
        return result
    prefix = orig.__module__ + '.' + orig.__name__ + '__mutmut_'
    if not mutant_under_test.startswith(prefix):
        # Check if orig is a bound method (has __self__) or plain function
        if self_arg is not None and not hasattr(orig, '__self__'):
            result = orig(self_arg, *call_args, **call_kwargs)
        else:
            result = orig(*call_args, **call_kwargs)
        return result
    mutant_name = mutant_under_test.rpartition('.')[-1]
    if self_arg is not None:
        # call to a class method where self is not bound
        result = mutants[mutant_name](self_arg, *call_args, **call_kwargs)
    else:
        result = mutants[mutant_name](*call_args, **call_kwargs)
    return result

""")
