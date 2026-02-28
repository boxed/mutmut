from mutmut.mutation.mutators import MethodType

CLASS_NAME_SEPARATOR = "ǁ"

GENERATED_MARKER = "# mutmut: generated"


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


def build_function_trampoline(
    *,
    orig_name: str,
    mutants: list[str],
    class_name: str | None,
    is_async: bool = False,
    is_async_generator: bool = False,
) -> str:
    mangled_name = mangle_function_name(name=orig_name, class_name=class_name)

    type_annotation = "ClassVar[MutantDict]" if class_name is not None else "MutantDict"
    mutants_dict = (
        f"{mangled_name}__mutmut_mutants : {type_annotation} = {{\n"
        + ", \n    ".join(f"{repr(m)}: {m}" for m in mutants)
        + "\n}"
    )
    access_prefix = ""
    access_suffix = ""
    self_arg = ""
    if class_name is not None:
        access_prefix = 'object.__getattribute__(self, "'
        access_suffix = '")'
        self_arg = ", self"

    trampoline_name = "_mutmut_trampoline"
    trampoline_call = f"{trampoline_name}({access_prefix}{mangled_name}__mutmut_orig{access_suffix}, {access_prefix}{mangled_name}__mutmut_mutants{access_suffix}, args, kwargs{self_arg})"
    self_prefix = "self, " if class_name is not None else ""

    if is_async_generator:
        body = f"""\
async def {orig_name}({self_prefix}*args, **kwargs):
    async for i in {trampoline_call}:
        yield i"""
    elif is_async:
        body = f"""\
async def {orig_name}({self_prefix}*args, **kwargs):
    result = await {trampoline_call}
    return result"""
    else:
        body = f"""\
def {orig_name}({self_prefix}*args, **kwargs):
    result = {trampoline_call}
    return result"""

    return _mark_generated(f"""
{mutants_dict}

{body}

{orig_name}.__signature__ = _mutmut_signature({mangled_name}__mutmut_orig)
{orig_name}.__annotations__ = {mangled_name}__mutmut_orig.__annotations__
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
    mutants_dict_entries = ", ".join(f"{repr(m)}: {prefix}_mutant_{i + 1}" for i, m in enumerate(mutant_names))
    mutants_dict = f"{prefix}_mutants = {{{mutants_dict_entries}}}"

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

    return _mark_generated(f"{mutants_dict}\n{orig_name_fix}\n{trampoline}")


# noinspection PyUnresolvedReferences
# language=python
trampoline_impl = _mark_generated("""
from inspect import signature as _mutmut_signature
from typing import Annotated
from typing import Callable
from typing import ClassVar


MutantDict = Annotated[dict[str, Callable], "Mutant"] # type: ignore


def _mutmut_trampoline(orig, mutants, call_args, call_kwargs, self_arg = None): # type: ignore
    \"""Forward call to original or mutated function, depending on the environment\"""
    import os # type: ignore
    mutant_under_test = os.environ.get('MUTANT_UNDER_TEST', '') # type: ignore
    if not mutant_under_test:
        # No mutant being tested - call original function
        if self_arg is not None and not hasattr(orig, '__self__'):
            return orig(self_arg, *call_args, **call_kwargs)
        else:
            return orig(*call_args, **call_kwargs)
    if mutant_under_test == 'fail': # type: ignore
        from mutmut.__main__ import MutmutProgrammaticFailException # type: ignore
        raise MutmutProgrammaticFailException('Failed programmatically')       # type: ignore
    elif mutant_under_test == 'stats': # type: ignore
        from mutmut.__main__ import record_trampoline_hit # type: ignore
        record_trampoline_hit(orig.__module__ + '.' + orig.__name__) # type: ignore
        # Check if orig is a bound method (has __self__) or plain function
        if self_arg is not None and not hasattr(orig, '__self__'): # type: ignore
            result = orig(self_arg, *call_args, **call_kwargs) # type: ignore
        else:
            result = orig(*call_args, **call_kwargs) # type: ignore
        return result # type: ignore
    prefix = orig.__module__ + '.' + orig.__name__ + '__mutmut_' # type: ignore
    if not mutant_under_test.startswith(prefix): # type: ignore
        # Check if orig is a bound method (has __self__) or plain function
        if self_arg is not None and not hasattr(orig, '__self__'): # type: ignore
            result = orig(self_arg, *call_args, **call_kwargs) # type: ignore
        else:
            result = orig(*call_args, **call_kwargs) # type: ignore
        return result # type: ignore
    mutant_name = mutant_under_test.rpartition('.')[-1] # type: ignore
    if self_arg is not None: # type: ignore
        # call to a class method where self is not bound
        result = mutants[mutant_name](self_arg, *call_args, **call_kwargs) # type: ignore
    else:
        result = mutants[mutant_name](*call_args, **call_kwargs) # type: ignore
    return result # type: ignore

""")
