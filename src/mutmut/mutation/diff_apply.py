"""Read functions back out of generated mutant files, to diff them or apply them to disk."""

from __future__ import annotations

from difflib import unified_diff
from pathlib import Path

import libcst as cst

from mutmut.mutation.data import MutantLineSpans
from mutmut.mutation.data import SourceFileMutationData
from mutmut.utils.file_utils import walk_mutatable_files
from mutmut.utils.format_utils import mangled_name_from_mutant_name
from mutmut.utils.format_utils import orig_function_and_class_names_from_key


def read_mutants_module(path: Path | str) -> cst.Module:
    with open(Path("mutants") / path) as f:
        return cst.parse_module(f.read())


def read_orig_module(path: Path | str) -> cst.Module:
    with open(path) as f:
        return cst.parse_module(f.read())


def find_top_level_function_or_method(module: cst.Module, name: str) -> cst.FunctionDef | None:
    name = name.split(".")[-1]
    for child in module.body:
        if isinstance(child, cst.FunctionDef) and child.name.value == name:
            return child
        if isinstance(child, cst.ClassDef) and isinstance(child.body, cst.IndentedBlock):
            for method in child.body.body:
                if isinstance(method, cst.FunctionDef) and method.name.value == name:
                    return method

    return None


def read_original_function(module: cst.Module, mutant_name: str) -> cst.FunctionDef:
    orig_function_name, _ = orig_function_and_class_names_from_key(mutant_name)
    orig_name = mangled_name_from_mutant_name(mutant_name) + "__mutmut_orig"

    result = find_top_level_function_or_method(module, orig_name)
    if not result:
        raise FileNotFoundError(f'Could not find original function "{orig_function_name}"')
    return result.with_changes(name=cst.Name(orig_function_name))


def read_mutant_function(module: cst.Module, mutant_name: str) -> cst.FunctionDef:
    orig_function_name, _ = orig_function_and_class_names_from_key(mutant_name)

    result = find_top_level_function_or_method(module, mutant_name)
    if not result:
        raise FileNotFoundError(f'Could not find original function "{orig_function_name}"')
    return result.with_changes(name=cst.Name(orig_function_name))


def find_mutant(mutant_name: str) -> SourceFileMutationData:
    for path in walk_mutatable_files():
        m = SourceFileMutationData(path=path)
        m.load()
        if mutant_name in m.exit_code_by_key:
            return m

    raise FileNotFoundError(f"Could not find mutant {mutant_name}")


def generated_function_names(mutant_name: str) -> tuple[str, str]:
    """Get the names of the generated original and mutated function for a mutant.

    :return: A tuple of (name of the unmutated copy, name of the mutant)."""
    generated_mutant_name = mutant_name.rpartition(".")[-1]
    return mangled_name_from_mutant_name(generated_mutant_name) + "__mutmut_orig", generated_mutant_name


def read_functions_from_index(mutant_name: str, path: Path | str) -> tuple[cst.FunctionDef, cst.FunctionDef] | None:
    """Read the unmutated copy and the mutant of a function from a mutated file, using the line span index.

    Only the lines of those two functions are parsed, instead of the whole mutated file.

    Both functions are named after the function they were generated from, so that a diff of the
    two shows only the mutation.

    :return: A tuple of (unmutated function, mutated function), or None if there is no usable index."""
    line_spans = MutantLineSpans.load(path)
    if line_spans is None:
        return None

    orig_name, generated_mutant_name = generated_function_names(mutant_name)
    try:
        sources = line_spans.read_function_sources([orig_name, generated_mutant_name])
    except (KeyError, ValueError):
        # the index is incomplete or malformed, so fall back to parsing the file
        return None

    orig_function_name, class_name = orig_function_and_class_names_from_key(mutant_name)
    orig_source, mutant_source = sources
    orig_function = parse_generated_function(orig_source, name=orig_name, is_method=class_name is not None)
    mutant_function = parse_generated_function(
        mutant_source, name=generated_mutant_name, is_method=class_name is not None
    )
    if orig_function is None or mutant_function is None:
        # the index does not match the mutated file, so fall back to parsing the file
        return None

    return (
        orig_function.with_changes(name=cst.Name(orig_function_name)),
        mutant_function.with_changes(name=cst.Name(orig_function_name)),
    )


def parse_generated_function(source: str, *, name: str, is_method: bool) -> cst.FunctionDef | None:
    """Parse a function that was read out of a mutated file by itself.

    :param source: The source of the function, still indented as it was in the file.
    :param is_method: Whether the function is a method, and therefore indented.
    :return: The function, or None if `source` does not contain a function called `name`."""
    if is_method:
        # the source is indented as a class body, so it needs a class to live in to parse
        source = "class _:\n" + source

    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError:
        # the index points at lines that are not a function, so it must be out of date
        return None

    function = find_top_level_function_or_method(module, name)
    if function is None:
        return None

    # comments and blank lines above the function became the module header when parsing it on its
    # own, but they belong to the function
    return function.with_changes(leading_lines=[*module.header, *function.leading_lines])


def get_diff_for_mutant(
    mutant_name: str,
    source: str | None = None,
    path: Path | str | None = None,
) -> str:
    if path is None:
        path = find_mutant(mutant_name).path

    functions = None if source is not None else read_functions_from_index(mutant_name, path)
    if functions is None:
        module = read_mutants_module(path) if source is None else cst.parse_module(source)
        functions = (read_original_function(module, mutant_name), read_mutant_function(module, mutant_name))

    orig_code, mutant_code = (cst.Module([function]).code.strip() for function in functions)

    path_str = str(path)
    return "\n".join(
        [
            line
            for line in unified_diff(
                orig_code.split("\n"), mutant_code.split("\n"), fromfile=path_str, tofile=path_str, lineterm=""
            )
        ]
    )


def apply_mutant(mutant_name: str) -> None:
    path = find_mutant(mutant_name).path

    orig_function_name, _ = orig_function_and_class_names_from_key(mutant_name)
    orig_function_name = orig_function_name.rpartition(".")[-1]

    orig_module = read_orig_module(path)

    original_function = find_top_level_function_or_method(orig_module, orig_function_name)
    if not original_function:
        raise FileNotFoundError(f"Could not apply mutant {mutant_name}")

    functions_from_index = read_functions_from_index(mutant_name, path)
    if functions_from_index is not None:
        _, mutant_function = functions_from_index
    else:
        mutant_function = read_mutant_function(read_mutants_module(path), mutant_name)
    mutant_function = mutant_function.with_changes(name=cst.Name(orig_function_name))

    new_module: cst.Module = orig_module.deep_replace(original_function, mutant_function)  # type: ignore[arg-type]

    with open(path, "w") as f:
        f.write(new_module.code)
