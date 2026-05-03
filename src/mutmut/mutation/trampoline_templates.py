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
    mangled_name: str,
    mutants: list[str],
    mutants_dict_name: str,
    class_name: str | None,
) -> str:
    """Fills the mutants dictionary with the mutant name -> method mappings

    :param mangled_name: The mangled function name
    :param mutants: List of mutant function names (mangled)
    :param mutants_dict_name: Variable name of the dictionary containing the mutants
    :return: String containing the mutants dict assignments
    """
    lines = []
    class_prefix = f"{class_name}." if class_name else ""
    lines.append(f"{mutants_dict_name}['_mutmut_orig'] = {class_prefix}{mangled_name}_orig")
    for mutant_name in mutants:
        lines.append(f"{mutants_dict_name}['{mutant_name}'] = {class_prefix}{mutant_name}")

    return _mark_generated("\n".join(lines))


# noinspection PyUnresolvedReferences
# language=python
trampoline_imports = """
from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict
"""
