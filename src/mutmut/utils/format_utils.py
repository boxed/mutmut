"""Utility functions for mutmut name formatting and key generation."""

import os
from pathlib import Path

from mutmut.mutation.trampoline_templates import CLASS_NAME_SEPARATOR


def make_mutant_key(func_name: str, class_name: str | None = None) -> str:
    """Create a consistent key for identifying a function/method for mutation tracking.

    :param func_name: The function or method name
    :param class_name: The containing class name, or None for top-level functions
    :return: A key string like "xǁMyClassǁmethod" for methods or "x_foo" for functions
    """
    if class_name:
        return f"x{CLASS_NAME_SEPARATOR}{class_name}{CLASS_NAME_SEPARATOR}{func_name}"
    else:
        return f"x_{func_name}"


def parse_mutant_key(key: str) -> tuple[str, str | None]:
    """Parse a mutant key back into function name and optional class name.

    :param key: A key string like "xǁMyClassǁmethod" or "x_foo"
    :return: A tuple of (func_name, class_name) where class_name is None for top-level functions
    """
    if CLASS_NAME_SEPARATOR in key:
        class_name = key[key.index(CLASS_NAME_SEPARATOR) + 1 : key.rindex(CLASS_NAME_SEPARATOR)]
        func_name = key[key.rindex(CLASS_NAME_SEPARATOR) + 1 :]
        return func_name, class_name
    else:
        assert key.startswith("x_"), f"Invalid key format: {key}"
        return key[2:], None


def is_mutated_method_name(name: str) -> bool:
    return name.startswith(("x_", "xǁ")) and "__mutmut" in name


def strip_prefix(s: str, *, prefix: str, strict: bool = False) -> str:
    if s.startswith(prefix):
        return s[len(prefix) :]
    assert strict is False, f"String '{s}' does not start with prefix '{prefix}'"
    return s


def get_mutant_name(relative_source_path: Path, mutant_method_name: str) -> str:
    module_name = str(relative_source_path)[: -len(relative_source_path.suffix)].replace(os.sep, ".")
    module_name = strip_prefix(module_name, prefix="src.")

    # FYI, we currently use "mutant_name" inconsistently, for both the whole identifier including the path and only the mangled method name
    mutant_name = f"{module_name}.{mutant_method_name}"
    mutant_name = mutant_name.replace(".__init__.", ".")
    return mutant_name
