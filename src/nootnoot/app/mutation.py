from __future__ import annotations

import ast
import fnmatch
import inspect
import os
import shutil
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import unified_diff
from multiprocessing import Pool
from os import walk
from pathlib import Path
from typing import TYPE_CHECKING, TextIO, cast

import libcst as cst

from nootnoot.app.code_coverage import gather_coverage, get_covered_lines_for_file
from nootnoot.app.config import get_config
from nootnoot.app.meta import SourceFileMutationData
from nootnoot.app.runners import PytestRunner
from nootnoot.app.state import NootNootState, get_state
from nootnoot.core import trampoline_runtime
from nootnoot.core.file_mutation import mutate_file_contents
from nootnoot.core.trampoline_templates import CLASS_NAME_SEPARATOR

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence
else:
    Iterable = object
    Iterator = object
    Sequence = object

status_by_exit_code = defaultdict(
    lambda: "suspicious",
    {
        1: "killed",
        3: "killed",
        0: "survived",
        5: "no tests",
        2: "check was interrupted by user",
        None: "not checked",
        33: "no tests",
        34: "skipped",
        35: "suspicious",
        36: "timeout",
        -24: "timeout",
        24: "timeout",
        152: "timeout",
        255: "timeout",
        -11: "segfault",
        -9: "segfault",
    },
)

emoji_by_status = {
    "survived": "🙁",
    "no tests": "🫥",
    "timeout": "⏰",
    "suspicious": "🤔",
    "skipped": "🔇",
    "check was interrupted by user": "🛑",
    "not checked": "?",
    "killed": "🎉",
    "segfault": "💥",
}

exit_code_to_emoji = {exit_code: emoji_by_status[status] for exit_code, status in status_by_exit_code.items()}


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class InvalidGeneratedSyntaxException(Exception):
    def __init__(self, file: Path | str) -> None:
        super().__init__(
            f"NootNoot generated invalid python syntax for {file}. "
            "If the original file has valid python syntax, please file an issue "
            "with a minimal reproducible example file."
        )


def record_trampoline_hit(name: str, state: NootNootState | None = None) -> None:
    if state is None:
        trampoline_runtime.record_trampoline_hit(name)
        return
    if name.startswith("src."):
        msg = "Failed trampoline hit. Module name starts with `src.`, which is invalid"
        raise ValueError(msg)
    config = get_config(state)
    if config.max_stack_depth != -1:
        f = inspect.currentframe()
        c = config.max_stack_depth
        while c and f:
            filename = f.f_code.co_filename
            if "pytest" in filename or "hammett" in filename or "unittest" in filename:
                break
            f = f.f_back
            c -= 1

        if not c:
            return

    state.add_stat(name)


NootNootProgrammaticFailException = trampoline_runtime.NootNootProgrammaticFailException


def _get_max_stack_depth() -> int:
    state = get_state()
    config = get_config(state)
    return config.max_stack_depth


def _add_stat(name: str) -> None:
    state = get_state()
    state.add_stat(name)


trampoline_runtime.register_trampoline_hooks(
    get_max_stack_depth=_get_max_stack_depth,
    add_stat=_add_stat,
)


def walk_all_files(state: NootNootState) -> Iterator[tuple[str, str]]:
    config = get_config(state)
    for path in config.paths_to_mutate:
        if not path.is_dir() and path.is_file():
            yield "", str(path)
            continue
        for root, _dirs, files in walk(path):
            for filename in files:
                yield root, filename


def walk_source_files(state: NootNootState) -> Iterator[Path]:
    for root, filename in walk_all_files(state):
        if filename.endswith(".py"):
            yield Path(root) / filename


@dataclass
class FileMutationResult:
    warnings: list[Warning]
    error: Exception | None = None


@dataclass
class Stat:
    not_checked: int
    killed: int
    survived: int
    total: int
    no_tests: int
    skipped: int
    suspicious: int
    timeout: int
    check_was_interrupted_by_user: int
    segfault: int


def create_mutants(max_children: int, state: NootNootState) -> None:
    with Pool(processes=max_children) as p:
        for result in p.imap_unordered(
            _create_file_mutants_with_state,
            [(path, state) for path in walk_source_files(state)],
        ):
            for warning in result.warnings:
                warnings.warn(warning, stacklevel=2)
            if result.error:
                raise result.error


def _create_file_mutants_with_state(args: tuple[Path, NootNootState]) -> FileMutationResult:
    path, state = args
    return create_file_mutants(path, state)


def create_file_mutants(path: Path, state: NootNootState) -> FileMutationResult:
    try:
        print(path, file=sys.stderr)
        output_path = Path("mutants") / path
        Path(output_path.parent).mkdir(exist_ok=True, parents=True)

        config = get_config(state)
        if config.should_ignore_for_mutation(path):
            shutil.copy(path, output_path)
            return FileMutationResult(warnings=[])
        return create_mutants_for_file(path, output_path, state)
    except Exception as e:  # noqa: BLE001
        return FileMutationResult(warnings=[], error=e)


def copy_src_dir(state: NootNootState) -> None:
    config = get_config(state)
    for path in config.paths_to_mutate:
        output_path: Path = Path("mutants") / path
        if path.is_dir():
            shutil.copytree(path, output_path, dirs_exist_ok=True)
        else:
            output_path.parent.mkdir(exist_ok=True, parents=True)
            shutil.copyfile(path, output_path)


def setup_source_paths():
    source_code_paths = [Path(), Path("src"), Path("source")]
    for path in source_code_paths:
        mutated_path = Path("mutants") / path
        if mutated_path.exists():
            sys.path.insert(0, str(mutated_path.absolute()))

    for path in source_code_paths:
        for i in range(len(sys.path)):
            while i < len(sys.path) and Path(sys.path[i]).resolve() == path.resolve():
                del sys.path[i]


def store_lines_covered_by_tests(state: NootNootState) -> None:
    config = get_config(state)
    if config.mutate_only_covered_lines:
        covered_lines = gather_coverage(PytestRunner(state), list(walk_source_files(state)))
        state.covered_lines = covered_lines


def copy_also_copy_files(state: NootNootState) -> None:
    config = get_config(state)
    if not isinstance(config.also_copy, list):
        msg = "config.also_copy must be a list of paths"
        raise TypeError(msg)
    for path_to_copy in config.also_copy:
        print("     also copying", path_to_copy, file=sys.stderr)
        source_path = Path(path_to_copy)
        destination = Path("mutants") / source_path
        if not source_path.exists():
            continue
        if source_path.is_file():
            shutil.copy(source_path, destination)
        else:
            shutil.copytree(source_path, destination, dirs_exist_ok=True)


def create_mutants_for_file(filename: Path, output_path: Path, state: NootNootState) -> FileMutationResult:
    input_stat = filename.stat()
    warnings_list: list[Warning] = []

    source = filename.read_text(encoding="utf-8")

    with output_path.open("w", encoding="utf-8") as out:
        try:
            mutant_names = write_all_mutants_to_file(
                out=out,
                source=source,
                filename=filename,
                state=state,
            )
        except cst.ParserSyntaxError as e:
            warnings_list.append(SyntaxWarning(f"Unsupported syntax in {filename} ({e!s}), skipping"))
            out.write(source)
            mutant_names = []

    try:
        ast.parse(output_path.read_text(encoding="utf-8"))
    except (IndentationError, SyntaxError) as e:
        invalid_syntax_error = InvalidGeneratedSyntaxException(output_path)
        invalid_syntax_error.__cause__ = e
        return FileMutationResult(warnings=warnings_list, error=invalid_syntax_error)

    source_file_mutation_data = SourceFileMutationData(path=filename)
    module_name = strip_prefix(str(filename)[: -len(filename.suffix)].replace(os.sep, "."), prefix="src.")

    source_file_mutation_data.exit_code_by_key = {
        f"{module_name}.{x}".replace(".__init__.", "."): None for x in mutant_names
    }
    source_file_mutation_data.save()

    os.utime(output_path, (input_stat.st_atime, input_stat.st_mtime))
    return FileMutationResult(warnings=warnings_list)


def write_all_mutants_to_file(
    *,
    out: TextIO,
    source: str,
    filename: str | Path,
    state: NootNootState,
) -> Sequence[str]:
    covered_lines = state.covered_lines
    result, mutant_names = mutate_file_contents(
        str(filename),
        source,
        get_covered_lines_for_file(filename, covered_lines),
    )
    out.write(result)

    return mutant_names


def unused(*_: object) -> None:
    return


def collected_test_names(state: NootNootState) -> set[str]:
    return set(state.duration_by_test.keys())


def strip_prefix(s: str, *, prefix: str, strict: bool = False) -> str:
    if s.startswith(prefix):
        return s[len(prefix) :]
    if strict:
        msg = f"String '{s}' does not start with prefix '{prefix}'"
        raise ValueError(msg)
    return s


def mangled_name_from_mutant_name(mutant_name: str) -> str:
    if "__nootnoot_" not in mutant_name:
        msg = f"{mutant_name} is not a valid mutant name"
        raise ValueError(msg)
    return mutant_name.partition("__nootnoot_")[0]


def orig_function_and_class_names_from_key(mutant_name: str) -> tuple[str, str | None]:
    r = mangled_name_from_mutant_name(mutant_name)
    _, _, r = r.rpartition(".")
    class_name = None
    if CLASS_NAME_SEPARATOR in r:
        class_name = r[r.index(CLASS_NAME_SEPARATOR) + 1 : r.rindex(CLASS_NAME_SEPARATOR)]
        r = r[r.rindex(CLASS_NAME_SEPARATOR) + 1 :]
    else:
        if not r.startswith("x_"):
            msg = f"Invalid mutant key: {mutant_name}"
            raise ValueError(msg)
        r = r[2:]
    return r, class_name


def collect_stat(m: SourceFileMutationData) -> Stat:
    r = {k.replace(" ", "_"): 0 for k in status_by_exit_code.values()}
    for v in m.exit_code_by_key.values():
        r[status_by_exit_code[v].replace(" ", "_")] += 1
    return Stat(
        **r,
        total=sum(r.values()),
    )


def calculate_summary_stats(source_file_mutation_data_by_path: dict[str, SourceFileMutationData]) -> Stat:
    stats = [collect_stat(x) for x in source_file_mutation_data_by_path.values()]
    return Stat(
        not_checked=sum(x.not_checked for x in stats),
        killed=sum(x.killed for x in stats),
        survived=sum(x.survived for x in stats),
        total=sum(x.total for x in stats),
        no_tests=sum(x.no_tests for x in stats),
        skipped=sum(x.skipped for x in stats),
        suspicious=sum(x.suspicious for x in stats),
        timeout=sum(x.timeout for x in stats),
        check_was_interrupted_by_user=sum(x.check_was_interrupted_by_user for x in stats),
        segfault=sum(x.segfault for x in stats),
    )


def collect_source_file_mutation_data(
    *, mutant_names: Iterable[str], state: NootNootState
) -> tuple[list[tuple[SourceFileMutationData, str, int | None]], dict[str, SourceFileMutationData]]:
    source_file_mutation_data_by_path: dict[str, SourceFileMutationData] = {}
    config = get_config(state)

    for path in walk_source_files(state):
        if config.should_ignore_for_mutation(path):
            continue
        if path in source_file_mutation_data_by_path:
            msg = f"Duplicate source file entry detected: {path}"
            raise ValueError(msg)
        m = SourceFileMutationData(path=path)
        m.load(debug=config.debug)
        source_file_mutation_data_by_path[str(path)] = m

    mutants = [
        (m, mutant_name, result)
        for path, m in source_file_mutation_data_by_path.items()
        for mutant_name, result in m.exit_code_by_key.items()
    ]

    if mutant_names:
        filtered_mutants = [
            (m, key, result)
            for m, key, result in mutants
            if key in mutant_names or any(fnmatch.fnmatch(key, mutant_name) for mutant_name in mutant_names)
        ]
        if not filtered_mutants:
            msg = f"Filtered for specific mutants, but nothing matches. Filters: {mutant_names}"
            raise ValueError(msg)
        mutants = filtered_mutants
    return mutants, source_file_mutation_data_by_path


def estimated_worst_case_time(state: NootNootState, mutant_name: str) -> float:
    tests = state.tests_by_mangled_function_name.get(mangled_name_from_mutant_name(mutant_name), set())
    return sum(state.duration_by_test[t] for t in tests)


def tests_for_mutant_names(state: NootNootState, mutant_names: Iterable[str]) -> set[str]:
    tests: set[str] = set()
    for mutant_name in mutant_names:
        if "*" in mutant_name:
            for name, tests_of_this_name in state.tests_by_mangled_function_name.items():
                if fnmatch.fnmatch(name, mutant_name):
                    tests |= set(tests_of_this_name)
        else:
            tests |= set(state.tests_by_mangled_function_name[mangled_name_from_mutant_name(mutant_name)])
    return tests


def read_mutants_module(path: str | Path) -> cst.Module:
    mutants_path = Path("mutants") / path
    return cst.parse_module(mutants_path.read_text(encoding="utf-8"))


def read_orig_module(path: str | Path) -> cst.Module:
    return cst.parse_module(Path(path).read_text(encoding="utf-8"))


def find_top_level_function_or_method(module: cst.Module, name: str) -> cst.FunctionDef | None:
    name = name.rsplit(".", maxsplit=1)[-1]
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
    orig_name = mangled_name_from_mutant_name(mutant_name) + "__nootnoot_orig"

    result = find_top_level_function_or_method(module, orig_name)
    if not result:
        msg = f'Could not find original function "{orig_function_name}"'
        raise FileNotFoundError(msg)
    return result.with_changes(name=cst.Name(orig_function_name))


def read_mutant_function(module: cst.Module, mutant_name: str) -> cst.FunctionDef:
    orig_function_name, _ = orig_function_and_class_names_from_key(mutant_name)

    result = find_top_level_function_or_method(module, mutant_name)
    if not result:
        msg = f'Could not find original function "{orig_function_name}"'
        raise FileNotFoundError(msg)
    return result.with_changes(name=cst.Name(orig_function_name))


def find_mutant(state: NootNootState, mutant_name: str) -> SourceFileMutationData:
    config = get_config(state)
    for path in walk_source_files(state):
        if config.should_ignore_for_mutation(path):
            continue

        m = SourceFileMutationData(path=path)
        m.load(debug=config.debug)
        if mutant_name in m.exit_code_by_key:
            return m

    msg = f"Could not find mutant {mutant_name}"
    raise FileNotFoundError(msg)


def get_diff_for_mutant(
    state: NootNootState,
    mutant_name: str,
    source: str | None = None,
    path: str | Path | None = None,
) -> str:
    if path is None:
        m = find_mutant(state, mutant_name)
        path = m.path

    module = read_mutants_module(path) if source is None else cst.parse_module(source)
    orig_code = cst.Module([read_original_function(module, mutant_name)]).code.strip()
    mutant_code = cst.Module([read_mutant_function(module, mutant_name)]).code.strip()

    path = str(path)
    return "\n".join([
        line
        for line in unified_diff(
            orig_code.split("\n"), mutant_code.split("\n"), fromfile=path, tofile=path, lineterm=""
        )
    ])


def apply_mutant(state: NootNootState, mutant_name: str) -> None:
    path = find_mutant(state, mutant_name).path

    orig_function_name, _class_name = orig_function_and_class_names_from_key(mutant_name)
    orig_function_name = orig_function_name.rpartition(".")[-1]

    orig_module = read_orig_module(path)
    mutants_module = read_mutants_module(path)

    mutant_function = read_mutant_function(mutants_module, mutant_name)
    mutant_function = mutant_function.with_changes(name=cst.Name(orig_function_name))

    original_function = find_top_level_function_or_method(orig_module, orig_function_name)
    if not original_function:
        msg = f"Could not apply mutant {mutant_name}"
        raise FileNotFoundError(msg)

    new_module = cast("cst.Module", orig_module.deep_replace(original_function, mutant_function))

    Path(path).write_text(new_module.code, encoding="utf-8")
