"""Utility functions for mutmut name formatting and key generation."""

import os
from pathlib import Path

CLASS_NAME_SEPARATOR = "ǁ"


def mangle_function_name(*, name: str, class_name: str | None) -> str:
    assert CLASS_NAME_SEPARATOR not in name
    if class_name:
        assert CLASS_NAME_SEPARATOR not in class_name
        prefix = f"x{CLASS_NAME_SEPARATOR}{class_name}{CLASS_NAME_SEPARATOR}"
    else:
        prefix = "x_"
    return f"{prefix}{name}"


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


def get_module_from_key(key: str) -> str:
    """Extract module name from a mangled function key like 'app.foo.x_bar'.

    The function name starts with 'x_' or 'xǁ', so we find that part
    and return everything before it as the module path.
    """
    parts = key.split(".")
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].startswith("x_") or parts[i].startswith("x\u01c1"):
            return ".".join(parts[:i])
    return key.rsplit(".", 1)[0] if "." in key else key


def mangled_name_from_mutant_name(mutant_name: str) -> str:
    assert "__mutmut_" in mutant_name, mutant_name
    return mutant_name.partition("__mutmut_")[0]


def orig_function_and_class_names_from_key(mutant_name: str) -> tuple[str, str | None]:
    r = mangled_name_from_mutant_name(mutant_name)
    _, _, r = r.rpartition(".")
    class_name = None
    if CLASS_NAME_SEPARATOR in r:
        class_name = r[r.index(CLASS_NAME_SEPARATOR) + 1 : r.rindex(CLASS_NAME_SEPARATOR)]
        r = r[r.rindex(CLASS_NAME_SEPARATOR) + 1 :]
    else:
        assert r.startswith("x_"), r
        r = r[2:]
    return r, class_name
