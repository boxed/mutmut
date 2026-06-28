from __future__ import annotations

import os
import platform
import sys
from collections.abc import Iterable
from collections.abc import Iterator
from typing import TYPE_CHECKING
from typing import Any

from mutmut.state import state
from mutmut.utils.file_utils import change_cwd
from mutmut.utils.format_utils import get_module_from_key
from mutmut.utils.format_utils import get_mutant_name
from mutmut.utils.format_utils import strip_prefix

if platform.system() == "Windows":
    print(
        "To run mutmut on Windows, please use the WSL. Native windows support is tracked in issue https://github.com/boxed/mutmut/issues/397"
    )
    sys.exit(1)
import ast
import fnmatch
import gc
import hashlib
import inspect
import itertools
import json
import resource
import shutil
import subprocess
import warnings
from abc import ABC
from collections import defaultdict
from collections.abc import Callable
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta
from difflib import unified_diff
from io import TextIOBase
from json import JSONDecodeError
from math import ceil
from multiprocessing import Pool
from multiprocessing import get_start_method
from multiprocessing import set_start_method
from os import makedirs
from os import walk
from os.path import isdir
from os.path import isfile
from pathlib import Path
from threading import Thread
from time import process_time
from types import TracebackType

import click
import libcst as cst
from rich.text import Text

import mutmut
from mutmut.code_coverage import gather_coverage
from mutmut.code_coverage import get_covered_lines_for_file
from mutmut.configuration import Config
from mutmut.mutation.data import SourceFileMutationData
from mutmut.mutation.file_mutation import FailedTypeCheckMutant
from mutmut.mutation.file_mutation import filter_mutants_with_type_checker
from mutmut.mutation.file_mutation import mutate_file_contents
from mutmut.mutation.trampoline_templates import CLASS_NAME_SEPARATOR
from mutmut.threading.timeout import register_timeout
from mutmut.utils.safe_setproctitle import safe_setproctitle as setproctitle

if TYPE_CHECKING:
    from coverage import Coverage

# Document: surviving mutants are retested when you ask mutmut to retest them, interactively in the UI or via command line

# TODO: pragma no mutate should end up in `skipped` category


status_by_exit_code = defaultdict(
    lambda: "suspicious",
    {
        1: "killed",
        3: "killed",  # internal error in pytest means a kill
        -24: "killed",
        0: "survived",
        5: "no tests",
        2: "check was interrupted by user",
        None: "not checked",
        33: "no tests",
        34: "skipped",
        35: "suspicious",
        36: "timeout",
        37: "caught by type check",
        -24: "timeout",  # SIGXCPU
        24: "timeout",  # SIGXCPU
        152: "timeout",  # SIGXCPU
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
    "caught by type check": "🧙",
    "check was interrupted by user": "🛑",
    "not checked": "?",
    "killed": "🎉",
    "segfault": "💥",
}

exit_code_to_emoji = {exit_code: emoji_by_status[status] for exit_code, status in status_by_exit_code.items()}


def record_trampoline_hit(name: str, caller: str | None = None) -> None:
    assert not name.startswith("src."), "Failed trampoline hit. Module name starts with `src.`, which is invalid"

    mutated_source_paths = Config.get().resolved_mutated_source_paths

    if Config.get().max_stack_depth != -1:
        f = inspect.currentframe()
        c = Config.get().max_stack_depth
        while c and f:
            filename = f.f_code.co_filename
            f = f.f_back
            if "pytest" in filename or "hammett" in filename or "unittest" in filename:
                break
            file_path = Path(filename).resolve(strict=True)
            if any(path in file_path.parents for path in mutated_source_paths):
                # only include stack frames of user-code; exclude mutmut and 3rd library stack frames
                c -= 1

        if not c:
            return

    mutmut._stats.add(name)
    if caller is not None and Config.get().track_dependencies:
        state().function_dependencies[name].add(caller)


def walk_all_files() -> Iterator[tuple[str, str]]:
    for path in Config.get().source_paths:
        if not isdir(path):
            if isfile(path):
                yield "", str(path)
                continue
        for root, dirs, files in walk(path):
            for filename in files:
                # only yield actual files, no sockets/pipes/etc.
                if isfile(Path(root) / filename):
                    yield root, filename


def walk_source_files() -> Iterator[Path]:
    for root, filename in walk_all_files():
        if filename.endswith(".py"):
            yield Path(root) / filename


def walk_mutatable_files() -> Iterator[Path]:
    config = Config.get()
    for path in walk_source_files():
        if config.should_mutate(path):
            yield path


class MutmutProgrammaticFailException(Exception):
    pass


class CollectTestsFailedException(Exception):
    pass


class BadTestExecutionCommandsException(Exception):
    def __init__(self, pytest_args: list[str]) -> None:
        msg = f"Failed to run pytest with args: {pytest_args}. If your config sets debug=true, the original pytest error should be above."
        super().__init__(msg)


class InvalidGeneratedSyntaxException(Exception):
    def __init__(self, file: Path | str) -> None:
        super().__init__(
            f"Mutmut generated invalid python syntax for {file}. "
            "If the original file has valid python syntax, please file an issue "
            "with a minimal reproducible example file."
        )


def copy_src_dir() -> None:
    for root, name in walk_all_files():
        source_path = Path(root) / name
        target_path = Path("mutants") / root / name

        if target_path.exists():
            continue

        if isdir(source_path):
            shutil.copytree(source_path, target_path)
        else:
            target_path.parent.mkdir(exist_ok=True, parents=True)
            # copy mtime, so we later know that when source_mtime == target_mtime, the file is not (yet) mutated.
            shutil.copy2(source_path, target_path)


@dataclass
class FileMutationResult:
    """Dataclass to transfer warnings and errors from child processes to the parent"""

    warnings: list[Warning] = field(default_factory=list)
    error: Exception | None = None
    unmodified: bool = False
    ignored: bool = False
    changed_functions: set[str] | None = None
    current_hashes: dict[str, str] | None = None


@dataclass
class MutantGenerationStats:
    mutated: int = 0
    unmodified: int = 0
    ignored: int = 0


def create_mutants(max_children: int) -> MutantGenerationStats:
    stats = MutantGenerationStats()
    with Pool(processes=max_children) as p:
        for result in p.imap_unordered(create_file_mutants, walk_source_files()):
            for warning in result.warnings:
                warnings.warn(warning)
            if result.error:
                raise result.error
            if result.unmodified:
                stats.unmodified += 1
            elif result.ignored:
                stats.ignored += 1
            else:
                stats.mutated += 1
            if result.current_hashes:
                state().current_function_hashes.update(result.current_hashes)
    return stats


def create_file_mutants(path: Path) -> FileMutationResult:
    try:
        print(path)
        output_path = Path("mutants") / path
        makedirs(output_path.parent, exist_ok=True)

        if Config.get().should_mutate(path):
            return create_mutants_for_file(path, output_path)
        else:
            shutil.copy(path, output_path)
            return FileMutationResult(ignored=True)
    except Exception as e:
        return FileMutationResult(error=e)


def setup_source_paths() -> None:
    # ensure that the mutated source code can be imported by the tests
    source_code_paths = [Path("."), Path("src"), Path("source")]
    for path in source_code_paths:
        mutated_path = Path("mutants") / path
        if mutated_path.exists():
            sys.path.insert(0, str(mutated_path.absolute()))

    # ensure that the original code CANNOT be imported by the tests
    for path in source_code_paths:
        for i in range(len(sys.path)):
            while i < len(sys.path) and Path(sys.path[i]).resolve() == path.resolve():
                del sys.path[i]


def store_lines_covered_by_tests() -> None:
    if Config.get().mutate_only_covered_lines:
        mutmut._covered_lines = gather_coverage(PytestRunner(), list(walk_source_files()))


def copy_also_copy_files() -> None:
    assert isinstance(Config.get().also_copy, list)
    for path in Config.get().also_copy:
        print("     also copying", path)
        path = Path(path)
        destination = Path("mutants") / path
        if not path.exists():
            continue
        if path.is_file():
            shutil.copy2(path, destination)
        else:
            shutil.copytree(path, destination, dirs_exist_ok=True)


def create_mutants_for_file(filename: Path, output_path: Path) -> FileMutationResult:
    warnings: list[Warning] = []

    try:
        source_mtime = os.path.getmtime(filename)
        mutant_mtime = os.path.getmtime(output_path)
        # We have three possible cases here:
        # source_mtime > mutant_mtime: the source file was modified after the mutant has been created
        # source_mtime == mutant_mtime: only copied, otherwise the mutant file is untouched
        # source_mtime < mutant_mtime: the mutations have been saved after copying; source file untouched
        if source_mtime < mutant_mtime:
            data = SourceFileMutationData(path=filename)
            data.load()
            return FileMutationResult(
                unmodified=True,
                current_hashes={get_mutant_name(filename, func): h for func, h in data.hash_by_function_name.items()},
            )
    except OSError:
        pass

    with open(filename) as f:
        source = f.read()

    with open(output_path, "w") as out:
        try:
            mutant_names, hash_by_function_name = write_all_mutants_to_file(out=out, source=source, filename=filename)
        except cst.ParserSyntaxError as e:
            # if libcst cannot parse it, then copy the source without any mutations
            warnings.append(SyntaxWarning(f"Unsupported syntax in {filename} ({str(e)}), skipping"))
            out.write(source)
            mutant_names, hash_by_function_name = [], {}

    # validate no syntax errors of mutants
    with open(output_path) as f:
        try:
            ast.parse(f.read())
        except (IndentationError, SyntaxError) as e:
            invalid_syntax_error = InvalidGeneratedSyntaxException(output_path)
            invalid_syntax_error.__cause__ = e
            return FileMutationResult(warnings=warnings, error=invalid_syntax_error)

    data = SourceFileMutationData(path=filename)
    data.load()
    old_hashes = data.hash_by_function_name
    changed = {f for f, h in hash_by_function_name.items() if old_hashes.get(f) != h}

    merged: dict[str, int | None] = {}
    for name in mutant_names:
        key = get_mutant_name(filename, name)
        func = mangled_name_from_mutant_name(key).rpartition(".")[2]
        if func not in hash_by_function_name or func in changed:
            merged[key] = None
        else:
            merged[key] = data.exit_code_by_key.get(key)
    data.exit_code_by_key = merged
    data.hash_by_function_name = hash_by_function_name
    data.save()

    current_hashes_qualified = {get_mutant_name(filename, func): h for func, h in hash_by_function_name.items()}
    changed_functions_qualified = {get_mutant_name(filename, func) for func in changed}

    return FileMutationResult(
        warnings=warnings,
        changed_functions=changed_functions_qualified,
        current_hashes=current_hashes_qualified,
    )


def write_all_mutants_to_file(*, out: TextIOBase, source: str, filename: Path) -> tuple[Sequence[str], dict[str, str]]:
    result, mutant_names, hash_by_function_name = mutate_file_contents(
        str(filename), source, get_covered_lines_for_file(str(filename), mutmut._covered_lines)
    )
    out.write(result)

    return mutant_names, hash_by_function_name


def unused(*_: object) -> None:
    pass


class TestRunner(ABC):
    def run_stats(self, *, tests: Iterable[str]) -> int:
        raise NotImplementedError()

    def run_forced_fail(self) -> int:
        raise NotImplementedError()

    def prepare_main_test_run(self) -> None:
        pass

    def run_tests(self, *, mutant_name: str | None, tests: Iterable[str]) -> int:
        raise NotImplementedError()

    def collect_main_test_coverage(self, cov: Coverage) -> int:
        raise NotImplementedError()

    def list_all_tests(self) -> ListAllTestsResult:
        raise NotImplementedError()


def collected_test_names() -> set[str]:
    return set(mutmut.duration_by_test.keys())


class ListAllTestsResult:
    def __init__(self, *, ids: set[str]) -> None:
        assert isinstance(ids, set)
        self.ids = ids

    def clear_out_obsolete_test_names(self) -> None:
        count_before = sum(len(x) for x in mutmut.tests_by_mangled_function_name)
        mutmut.tests_by_mangled_function_name = defaultdict(
            set,
            **{
                k: {test_name for test_name in test_names if test_name in self.ids}
                for k, test_names in mutmut.tests_by_mangled_function_name.items()
            },
        )
        count_after = sum(len(x) for x in mutmut.tests_by_mangled_function_name)
        if count_before != count_after:
            print(f"Removed {count_before - count_after} obsolete test names")
            save_stats()

    def new_tests(self) -> set[str]:
        return self.ids - collected_test_names()


class PytestRunner(TestRunner):
    def __init__(self) -> None:
        self._pytest_add_cli_args: list[str] = Config.get().pytest_add_cli_args
        self._pytest_add_cli_args_test_selection: list[str] = Config.get().pytest_add_cli_args_test_selection

    # noinspection PyMethodMayBeStatic
    def execute_pytest(self, params: list[str], **kwargs: Any) -> int:
        import pytest

        params = ["--rootdir=.", "--tb=native"] + params + self._pytest_add_cli_args
        if Config.get().debug:
            params = ["-vv"] + params
            print("python -m pytest ", " ".join([f'"{param}"' for param in params]))
        exit_code = int(pytest.main(params, **kwargs))
        if Config.get().debug:
            print("    exit code", exit_code)
        if exit_code == 4:
            raise BadTestExecutionCommandsException(params)
        return exit_code

    def _pytest_args_regular_run(self, tests: Iterable[str]) -> list[str]:
        pytest_args = ["-x", "-q", "-p", "no:randomly", "-p", "no:random-order"]
        if tests:
            pytest_args += list(tests)
        else:
            pytest_args += self._pytest_add_cli_args_test_selection
        return pytest_args

    def run_stats(self, *, tests: Iterable[str]) -> int:
        class StatsCollector:
            # noinspection PyMethodMayBeStatic
            def pytest_runtest_logstart(self, nodeid: str, location: Any) -> None:
                mutmut.duration_by_test[nodeid] = 0

            # noinspection PyMethodMayBeStatic
            def pytest_runtest_teardown(self, item: Any, nextitem: Any) -> None:
                unused(nextitem)
                for function in mutmut._stats:
                    mutmut.tests_by_mangled_function_name[function].add(strip_prefix(item._nodeid, prefix="mutants/"))
                mutmut._stats.clear()

            # noinspection PyMethodMayBeStatic
            def pytest_runtest_makereport(self, item: Any, call: Any) -> None:
                mutmut.duration_by_test[item.nodeid] += call.duration

        stats_collector = StatsCollector()

        with change_cwd("mutants"):
            return int(self.execute_pytest(self._pytest_args_regular_run(tests), plugins=[stats_collector]))

    def run_tests(self, *, mutant_name: str | None, tests: Iterable[str]) -> int:
        with change_cwd("mutants"):
            return int(self.execute_pytest(self._pytest_args_regular_run(tests)))

    def collect_main_test_coverage(self, cov: Coverage) -> int:
        with change_cwd("mutants"), cov.collect():
            self.prepare_main_test_run()
            return int(self.execute_pytest(self._pytest_args_regular_run([])))

    def run_forced_fail(self) -> int:
        return self.run_tests(mutant_name=None, tests=[])

    def list_all_tests(self) -> ListAllTestsResult:
        class TestsCollector:
            def __init__(self) -> None:
                self.collected_nodeids: set[str] = set()
                self.deselected_nodeids: set[str] = set()

            def pytest_collection_modifyitems(self, items: Any) -> None:
                self.collected_nodeids |= {item.nodeid for item in items}

            def pytest_deselected(self, items: Any) -> None:
                self.deselected_nodeids |= {item.nodeid for item in items}

        collector = TestsCollector()

        pytest_args = ["-x", "-q", "--collect-only"] + self._pytest_add_cli_args_test_selection

        with change_cwd("mutants"):
            exit_code = int(self.execute_pytest(pytest_args, plugins=[collector]))
            if exit_code != 0:
                raise CollectTestsFailedException()

        selected_nodeids = collector.collected_nodeids - collector.deselected_nodeids
        return ListAllTestsResult(ids=selected_nodeids)


class HammettRunner(TestRunner):
    def __init__(self) -> None:
        self.hammett_kwargs: Any = None

    def run_stats(self, *, tests: Iterable[str]) -> int:
        import hammett

        print("Running hammett stats...")

        def post_test_callback(_name: str, **_: Any) -> None:
            for function in mutmut._stats:
                mutmut.tests_by_mangled_function_name[function].add(_name)
            mutmut._stats.clear()

        return int(
            hammett.main(
                quiet=True,
                fail_fast=True,
                disable_assert_analyze=True,
                post_test_callback=post_test_callback,
                use_cache=False,
                insert_cwd=False,
            )
        )

    def run_forced_fail(self) -> int:
        import hammett

        return int(
            hammett.main(quiet=True, fail_fast=True, disable_assert_analyze=True, use_cache=False, insert_cwd=False)
        )

    def prepare_main_test_run(self) -> None:
        import hammett

        self.hammett_kwargs = hammett.main_setup(
            quiet=True,
            fail_fast=True,
            disable_assert_analyze=True,
            use_cache=False,
            insert_cwd=False,
        )

    def run_tests(self, *, mutant_name: str | None, tests: Iterable[str]) -> int:
        import hammett

        hammett.Config.workerinput = dict(workerinput=f"_{mutant_name}")
        return int(hammett.main_run_tests(**self.hammett_kwargs, tests=tests))


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


spinner = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")


def status_printer() -> Callable[..., None]:
    """Manage the printing and in-place updating of a line of characters

    .. note::
        If the string is longer than a line, then in-place updating may not
        work (it will print a new line at each refresh).
    """
    last_len = [0]
    last_update = [datetime(1900, 1, 1)]
    update_threshold = timedelta(seconds=0.1)

    def p(s: str, *, force_output: bool = False) -> None:
        if not force_output and (datetime.now() - last_update[0]) < update_threshold:
            return
        s = next(spinner) + " " + s
        len_s = len(s)
        output = "\r" + s + (" " * max(last_len[0] - len_s, 0))
        assert sys.__stdout__ is not None
        sys.__stdout__.write(output)
        sys.__stdout__.flush()
        last_len[0] = len_s

    return p


print_status = status_printer()


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
    caught_by_type_check: int


def collect_stat(m: SourceFileMutationData) -> Stat:
    r = {k.replace(" ", "_"): 0 for k in status_by_exit_code.values()}
    for k, v in m.exit_code_by_key.items():
        # noinspection PyTypeChecker
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
        caught_by_type_check=sum(x.caught_by_type_check for x in stats),
    )


def print_stats(
    source_file_mutation_data_by_path: dict[str, SourceFileMutationData], force_output: bool = False
) -> None:
    s = calculate_summary_stats(source_file_mutation_data_by_path)
    print_status(
        f"{(s.total - s.not_checked)}/{s.total}  🎉 {s.killed} 🫥 {s.no_tests}  ⏰ {s.timeout}  🤔 {s.suspicious}  🙁 {s.survived}  🔇 {s.skipped}  🧙 {s.caught_by_type_check}",
        force_output=force_output,
    )


def run_forced_fail_test(runner: TestRunner) -> None:
    os.environ["MUTANT_UNDER_TEST"] = "fail"
    with CatchOutput(spinner_title="Running forced fail test") as catcher:
        try:
            if runner.run_forced_fail() == 0:
                catcher.dump_output()
                print("FAILED: Unable to force test failures")
                raise SystemExit(1)
        except MutmutProgrammaticFailException:
            pass
    os.environ["MUTANT_UNDER_TEST"] = ""
    print("    done")


class CatchOutput:
    def __init__(
        self,
        callback: Callable[[str], None] = lambda s: None,
        spinner_title: str | None = None,
    ) -> None:
        self.strings: list[str] = []
        self.spinner_title = spinner_title or ""
        if Config.get().debug:
            self.spinner_title += "\n"

        class StdOutRedirect(TextIOBase):
            def __init__(self, catcher: CatchOutput) -> None:
                self.catcher = catcher

            def write(self, s: str) -> int:
                callback(s)
                if spinner_title:
                    print_status(spinner_title)
                self.catcher.strings.append(s)
                return len(s)

        self.redirect = StdOutRedirect(self)

    # noinspection PyMethodMayBeStatic
    def stop(self) -> None:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    def start(self) -> None:
        if self.spinner_title:
            print_status(self.spinner_title)
        sys.stdout = self.redirect
        sys.stderr = self.redirect
        if Config.get().debug:
            self.stop()

    def dump_output(self) -> None:
        self.stop()
        print()
        for line in self.strings:
            print(line, end="")

    def __enter__(self) -> CatchOutput:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()
        if self.spinner_title:
            print()


@click.group()
@click.version_option()
def cli() -> None:
    pass


def run_stats_collection(runner: TestRunner, tests: Iterable[str] | None = None) -> None:
    if tests is None:
        tests = []  # Meaning all...

    os.environ["MUTANT_UNDER_TEST"] = "stats"
    os.environ["PY_IGNORE_IMPORTMISMATCH"] = "1"
    depth = Config.get().dependency_tracking_depth
    os.environ["MUTMUT_DEPENDENCY_DEPTH"] = str(depth)
    start_cpu_time = process_time()

    with CatchOutput(spinner_title="Running stats") as output_catcher:
        collect_stats_exit_code = runner.run_stats(tests=tests)
        if collect_stats_exit_code != 0:
            output_catcher.dump_output()
            print(f"failed to collect stats. runner returned {collect_stats_exit_code}")
            exit(1)
        num_associated_tests = sum(len(tests) for tests in mutmut.tests_by_mangled_function_name.values())
        if num_associated_tests == 0:
            output_catcher.dump_output()
            print(
                "Stopping early, because we could not find any test case for any mutant. It seems that the selected tests do not cover any code that we mutated."
            )
            if not Config.get().debug:
                print("You can set debug=true to see the executed test names in the output above.")
            else:
                print("In the last pytest run above, you can see which tests we executed.")
            print("You can use mutmut browse to check which parts of the source code we mutated.")
            print(
                "If some of the mutated code should be covered by the executed tests, consider opening an issue (with a MRE if possible)."
            )
            exit(1)

    print("    done")
    if not tests:  # again, meaning all
        mutmut.stats_time = process_time() - start_cpu_time

    if not collected_test_names():
        print("failed to collect stats, no active tests found")
        exit(1)

    save_stats()


def _cleanup_stale_stats() -> None:
    valid_modules = {get_module_from_key(key) for key in state().current_function_hashes}

    def _is_valid_key(key: str) -> bool:
        return get_module_from_key(key) in valid_modules

    stale_keys = [k for k in mutmut.tests_by_mangled_function_name if not _is_valid_key(k)]
    for k in stale_keys:
        del mutmut.tests_by_mangled_function_name[k]

    stale_dep_keys = [k for k in state().function_dependencies if not _is_valid_key(k)]
    for k in stale_dep_keys:
        del state().function_dependencies[k]

    for _, callers in state().function_dependencies.items():
        callers -= {c for c in callers if not _is_valid_key(c)}


def _invalidate_stale_dependency_edges() -> set[str]:
    old_hashes = state().old_function_hashes
    new_hashes = state().current_function_hashes

    if not old_hashes:
        return set()

    all_functions = old_hashes.keys() | new_hashes.keys()
    changed_functions = {f for f in all_functions if old_hashes.get(f) != new_hashes.get(f)}

    if not changed_functions:
        return set()

    for callers in state().function_dependencies.values():
        callers -= changed_functions

    deleted_functions = old_hashes.keys() - new_hashes.keys()
    for f in deleted_functions:
        state().function_dependencies.pop(f, None)

    return changed_functions


# Dependency / build files whose changes the per-function source hashes cannot see.
# Globs are resolved against the project root; missing files are skipped. Users can
# extend this via the ``cache_invalidation_files`` config.
_DEFAULT_WATCHED_FILES = (
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "requirements*.txt",
    "poetry.lock",
    "uv.lock",
    "Pipfile",
    "Pipfile.lock",
)

# Files that practically never affect test behavior. Git change detection otherwise
# surfaces every non-.py file in the repo, so these are dropped to cut the noise.
# Users extend this via the ``cache_invalidation_exclude`` config; anything they
# explicitly register in ``cache_invalidation_files`` is never excluded. Patterns are
# matched with fnmatch (``*`` spans path separators).
_DEFAULT_INVALIDATION_EXCLUDE = (
    "*.md",
    "*.rst",
    "LICENSE*",
    "COPYING*",
    "NOTICE*",
    "AUTHORS*",
    "CHANGELOG*",
    "CHANGES*",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".pre-commit-config.yaml",
    "docs/*",
    "doc/*",
)


def _hash_files(paths: Iterable[str]) -> dict[str, str]:
    """Content hash each existing path; missing files are simply omitted."""
    hashes: dict[str, str] = {}
    for p in paths:
        path = Path(p)
        if path.is_file():
            hashes[p] = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return hashes


def compute_watched_file_hashes() -> dict[str, str]:
    """Map watched-file path -> content hash for the default set plus user globs."""
    patterns = list(_DEFAULT_WATCHED_FILES) + list(Config.get().cache_invalidation_files)
    paths = [str(path) for pattern in patterns for path in sorted(Path(".").glob(pattern))]
    return _hash_files(paths)


def _run_git(args: list[str]) -> str | None:
    """Run a git command at the project root. Returns stdout, or None on any failure
    (git not installed, not a repo, unknown ref, ...). Git is a soft dependency: this
    never raises so callers can silently fall back to content hashing.
    """
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def git_head() -> str | None:
    """The current HEAD commit, or None when git / a repo / a commit is unavailable."""
    out = _run_git(["rev-parse", "HEAD"])
    return out.strip() if out else None


def git_changed_non_py_files(since_ref: str) -> set[str] | None:
    """Non-.py files changed since ``since_ref`` (tracked diffs against the working tree,
    including uncommitted edits, plus new untracked files). ``.py`` files are excluded
    because the per-function hashes already track them. Returns None if git cannot answer.
    """
    diff = _run_git(["diff", "--name-only", since_ref, "--"])
    if diff is None:
        return None
    untracked = _run_git(["ls-files", "--others", "--exclude-standard"]) or ""
    files = {line for line in (diff + "\n" + untracked).splitlines() if line}
    return {f for f in files if not f.endswith(".py")}


def git_tracked_non_py_files() -> set[str] | None:
    """Every non-.py file git knows about (tracked + untracked-not-ignored), or None if
    git cannot answer. Recorded on a full run so a later git-less run can still detect
    changes to these files by re-hashing them.
    """
    out = _run_git(["ls-files", "--cached", "--others", "--exclude-standard"])
    if out is None:
        return None
    return {line for line in out.splitlines() if line and not line.endswith(".py")}


def _changed_hashed_files(restrict_to: list[str] | None = None) -> set[str]:
    """Baseline files whose content changed, by re-hashing them now.

    Re-hashes every path in the stored baseline (which, after a full run with git, is
    the comprehensive set of non-.py files) plus any newly-appearing curated/user-glob
    files. This is how a git-less run still detects changes to files git discovered.
    ``restrict_to`` limits the result to paths matching those glob patterns.
    """
    old = state().old_watched_file_hashes
    if not old:
        return set()
    new = _hash_files(old.keys())
    new.update(compute_watched_file_hashes())  # pick up newly-added curated/user files
    changed = {p for p in old.keys() | new.keys() if old.get(p) != new.get(p)}
    if restrict_to is not None:
        changed = {p for p in changed if any(fnmatch.fnmatch(p, pat) for pat in restrict_to)}
    return changed


def _is_excluded(path: str, config: Config) -> bool:
    """Whether ``path`` should be dropped from change reporting as noise.

    Files explicitly registered in ``cache_invalidation_files`` are never excluded.
    """
    if any(fnmatch.fnmatch(path, pat) for pat in config.cache_invalidation_files):
        return False
    patterns = list(_DEFAULT_INVALIDATION_EXCLUDE) + list(config.cache_invalidation_exclude)
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def _changed_dependency_files() -> set[str]:
    """Files changed since the last full run that the per-function hashes cannot track.

    Prefers git (catches every non-.py file in the repo and respects .gitignore) and
    falls back to hashing a curated set of build/dependency files when git is
    unavailable. Silent on the first run (no baseline to compare against). Noisy files
    (see ``_DEFAULT_INVALIDATION_EXCLUDE`` and ``cache_invalidation_exclude``) are dropped.
    """
    config = Config.get()
    old_commit = state().old_git_commit
    if config.use_git_change_detection and old_commit is not None:
        git_changed = git_changed_non_py_files(old_commit)
        if git_changed is not None:
            # also catch explicitly-registered files that git ignores
            changed = git_changed | _changed_hashed_files(restrict_to=config.cache_invalidation_files)
        else:
            changed = _changed_hashed_files()
    else:
        changed = _changed_hashed_files()
    return {p for p in changed if not _is_excluded(p, config)}


def _compute_baseline_file_hashes() -> dict[str, str]:
    """The set of non-.py files to track, hashed. Always includes the curated/user-glob
    files; when git is available it also records every tracked non-.py file (minus noise)
    so a later git-less run can still detect changes to them.
    """
    config = Config.get()
    hashes = compute_watched_file_hashes()
    if config.use_git_change_detection:
        tracked = git_tracked_non_py_files()
        if tracked is not None:
            hashes.update(_hash_files(sorted(p for p in tracked if not _is_excluded(p, config))))
    return hashes


def _refresh_change_detection_baseline() -> None:
    """Snapshot the current git commit and tracked-file hashes as the new baseline.

    Only called on a full run; cached runs keep the previous baseline so a ``warn``
    keeps firing until the cache is actually rebuilt.
    """
    state().git_commit = git_head()
    state().watched_file_hashes = _compute_baseline_file_hashes()


def _reset_mutant_results(should_reset: Callable[[str, int], bool]) -> int:
    """Reset cached verdicts to ``None`` (forcing a re-test) where ``should_reset`` holds.

    ``should_reset`` only sees already-decided mutants (``exit_code`` is not ``None``).
    """
    count = 0
    for path in walk_mutatable_files():
        meta_path = Path("mutants") / (str(path) + ".meta")
        if not meta_path.exists():
            continue
        m = SourceFileMutationData(path=path)
        m.load()
        dirty = False
        for key, exit_code in list(m.exit_code_by_key.items()):
            if exit_code is not None and should_reset(key, exit_code):
                m.exit_code_by_key[key] = None
                dirty = True
                count += 1
        if dirty:
            m.save()
    return count


def _report_watched_file_changes() -> bool:
    """Surface non-Python files that changed since the last full run.

    Returns True only when the configured policy is ``rerun`` and something changed,
    asking the caller to reset all results. Silent when there is no baseline yet.
    """
    changed = _changed_dependency_files()
    if not changed:
        return False

    policy = Config.get().on_dependency_change
    if policy == "ignore":
        return False
    listed = sorted(changed)
    if policy == "rerun":
        print(f"    {len(listed)} non-Python file(s) changed; rerunning all mutants: {', '.join(listed)}")
        return True
    # default: warn but keep the cache
    print(f"    Warning: {len(listed)} non-Python file(s) changed since the last full run: {', '.join(listed)}")
    print("    These cannot be tracked for behavioral changes, so cached results were kept.")
    print('    If the changes affect your tests, delete the mutants/ directory or set on_dependency_change = "rerun".')
    return False


def _apply_config_change_invalidation(mutants_caught_by_type_checker: dict[str, object]) -> bool:
    """Reset only the cached verdicts a config / dependency change could have invalidated.

    Returns True if a full stats recollection is required (a global pytest config change
    or an opt-in dependency rerun), in which case all results have already been reset.
    """
    old_fp = state().old_config_fingerprint
    new_fp = Config.get().config_fingerprint()
    changed_groups = {g for g in new_fp if old_fp.get(g) != new_fp[g]} if old_fp else set()

    dependency_rerun = _report_watched_file_changes()

    # Global groups change how *every* test runs / which tests map to a function, so no
    # subset of results is safe to keep -> full reset and full stats recollection.
    if changed_groups & {"test_execution", "test_selection"} or dependency_rerun:
        _reset_mutant_results(lambda key, exit_code: True)
        mutmut.duration_by_test.clear()
        mutmut.tests_by_mangled_function_name.clear()
        state().function_dependencies.clear()
        return True

    # Timeout config only reclassifies timeouts; keep every other verdict.
    if "timeout" in changed_groups:
        _reset_mutant_results(lambda key, exit_code: status_by_exit_code[exit_code] == "timeout")

    # The type-check pre-filter runs fresh every run; only verdicts whose type-check
    # status flips are stale -> reset the symmetric difference of old (==37) and new.
    if "type_check" in changed_groups:
        caught = set(mutants_caught_by_type_checker)
        _reset_mutant_results(lambda key, exit_code: (exit_code == 37) != (key in caught))

    return False


def collect_or_load_stats(
    runner: TestRunner,
    *,
    mutants_caught_by_type_checker: dict[str, Any] | None = None,
    apply_config_invalidation: bool = False,
    invalidate_stale_callers: bool = True,
) -> None:
    did_load = load_stats()

    force_full = False
    if did_load and apply_config_invalidation:
        force_full = _apply_config_change_invalidation(mutants_caught_by_type_checker or {})

    if not did_load or force_full:
        # A full run rebuilds the cache, so reset the change-detection baseline to "now".
        _refresh_change_detection_baseline()
        # Run full stats
        run_stats_collection(runner)
    else:
        _cleanup_stale_stats()
        if Config.get().track_dependencies and invalidate_stale_callers:
            _invalidate_stale_dependency_edges()
        save_stats()

        # Run incremental stats
        with CatchOutput(spinner_title="Listing all tests") as output_catcher:
            os.environ["MUTANT_UNDER_TEST"] = "list_all_tests"
            try:
                all_tests_result = runner.list_all_tests()
            except CollectTestsFailedException:
                output_catcher.dump_output()
                print("Failed to collect list of tests")
                exit(1)

        all_tests_result.clear_out_obsolete_test_names()

        new_tests = all_tests_result.new_tests()

        if new_tests:
            print(f"Found {len(new_tests)} new tests, rerunning stats collection")
            run_stats_collection(runner, tests=new_tests)


def load_stats() -> bool:
    did_load = False
    try:
        with open("mutants/mutmut-stats.json") as f:
            data = json.load(f)
            for k, v in data.pop("tests_by_mangled_function_name").items():
                mutmut.tests_by_mangled_function_name[k] |= set(v)
            mutmut.duration_by_test = data.pop("duration_by_test")
            mutmut.stats_time = data.pop("stats_time")
            state().old_function_hashes = data.pop("function_hashes", {})
            for k, v in data.pop("function_dependencies", {}).items():
                state().function_dependencies[k] = set(v)
            state().old_config_fingerprint = data.pop("config_fingerprint", {})
            state().old_watched_file_hashes = data.pop("watched_file_hashes", {})
            state().old_git_commit = data.pop("git_commit", None)
            # Preserve the loaded baseline; only a full run refreshes it.
            state().watched_file_hashes = state().old_watched_file_hashes
            state().git_commit = state().old_git_commit
            assert not data, data
            did_load = True
    except (FileNotFoundError, JSONDecodeError):
        pass
    return did_load


def save_stats() -> None:
    with open("mutants/mutmut-stats.json", "w") as f:
        json.dump(
            dict(
                tests_by_mangled_function_name={k: list(v) for k, v in mutmut.tests_by_mangled_function_name.items()},
                duration_by_test=mutmut.duration_by_test,
                stats_time=mutmut.stats_time,
                function_hashes=state().current_function_hashes,
                function_dependencies={k: list(v) for k, v in state().function_dependencies.items()},
                config_fingerprint=Config.get().config_fingerprint(),
                watched_file_hashes=state().watched_file_hashes,
                git_commit=state().git_commit,
            ),
            f,
            indent=4,
        )


def save_cicd_stats(source_file_mutation_data_by_path: dict[str, SourceFileMutationData]) -> None:
    s = calculate_summary_stats(source_file_mutation_data_by_path)
    with open("mutants/mutmut-cicd-stats.json", "w") as f:
        json.dump(
            dict(
                killed=s.killed,
                survived=s.survived,
                total=s.total,
                no_tests=s.no_tests,
                skipped=s.skipped,
                suspicious=s.suspicious,
                timeout=s.timeout,
                check_was_interrupted_by_user=s.check_was_interrupted_by_user,
                segfault=s.segfault,
            ),
            f,
            indent=4,
        )


# exports CI/CD stats to block pull requests from merging if mutation score is too low, or used in other ways in CI/CD pipelines
@cli.command()
def export_cicd_stats() -> None:
    Config.ensure_loaded()

    source_file_mutation_data_by_path: dict[str, SourceFileMutationData] = {}

    for path in walk_mutatable_files():
        meta_path = Path("mutants") / (str(path) + ".meta")
        if not meta_path.exists():
            continue

        m = SourceFileMutationData(path=path)
        m.load()
        if not m.exit_code_by_key:
            continue

        source_file_mutation_data_by_path[str(path)] = m

    if not source_file_mutation_data_by_path:
        print('No previous mutation data found. Run "mutmut run" first.')
        return

    save_cicd_stats(source_file_mutation_data_by_path)
    print("Saved CI/CD stats to mutants/mutmut-cicd-stats.json")


def collect_source_file_mutation_data(
    *, mutant_names: tuple[str, ...] | list[str]
) -> tuple[
    list[tuple[SourceFileMutationData, str, int | None]],
    dict[str, SourceFileMutationData],
]:
    source_file_mutation_data_by_path: dict[str, SourceFileMutationData] = {}

    for path in walk_mutatable_files():
        assert str(path) not in source_file_mutation_data_by_path
        m = SourceFileMutationData(path=path)
        m.load()
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
        assert filtered_mutants, f"Filtered for specific mutants, but nothing matches\n\nFilter: {mutant_names}"
        mutants = filtered_mutants
    return mutants, source_file_mutation_data_by_path


def _check_test_to_mutant_associations(
    source_file_mutation_data_by_path: dict[str, SourceFileMutationData],
) -> None:
    """Detect when stats recorded trampoline hits but no recorded key matches any mutant key.

    The trampoline records ``orig.__module__ + '.' + orig.__name__`` while the
    per-mutant lookup uses the path-derived dotted name from ``get_mutant_name``.
    In a healthy project these are equal because the test suite imports the
    source via fully-qualified package paths and the source dir matches one of
    the conventions handled by ``setup_source_paths``. When they diverge (e.g.
    ``[tool.pytest.ini_options] pythonpath = ["pkg"]`` makes tests do
    ``import foo`` instead of ``from pkg.foo import ...``) every mutant is
    silently marked "No Tests" and the run reports 0.00 mutations/second.

    This check exits with an actionable message instead of producing the silent
    all-No-Tests outcome.
    """
    recorded = set(mutmut.tests_by_mangled_function_name.keys())
    if not recorded:
        # No hits at all - the existing zero-check in run_stats_collection
        # already covers this path; nothing to add here.
        return

    expected = {
        mangled_name_from_mutant_name(mutant_name)
        for m in source_file_mutation_data_by_path.values()
        for mutant_name in m.exit_code_by_key
    }
    if not expected or recorded & expected:
        return

    print(
        "Stopping early, because tests recorded trampoline hits but none match any mutant key. "
        "It looks like tests import the source under a different module path than mutmut sees from the file path."
    )
    print(f"Recorded keys (e.g.): {sorted(recorded)[:3]}")
    print(f"Expected keys (e.g.): {sorted(expected)[:3]}")
    print(
        "Common causes: a pythonpath setting in pytest config, conftest sys.path injection, "
        "or a source dir other than ./, src/, or source/."
    )
    print(
        "Fix: use fully-qualified package imports (e.g. from pkg.foo import ...) "
        "and rely on mutmut's default sys.path setup."
    )
    exit(1)


def estimated_worst_case_time(mutant_name: str) -> float:
    tests = mutmut.tests_by_mangled_function_name.get(mangled_name_from_mutant_name(mutant_name), set())
    return sum(mutmut.duration_by_test[t] for t in tests)


@cli.command()
@click.argument("mutant_names", required=False, nargs=-1)
def print_time_estimates(mutant_names: tuple[str, ...]) -> None:
    assert isinstance(mutant_names, (tuple, list)), mutant_names
    Config.ensure_loaded()

    runner = PytestRunner()
    runner.prepare_main_test_run()

    collect_or_load_stats(runner)

    mutants, source_file_mutation_data_by_path = collect_source_file_mutation_data(mutant_names=mutant_names)

    _check_test_to_mutant_associations(source_file_mutation_data_by_path)

    times_and_keys = [(estimated_worst_case_time(mutant_name), mutant_name) for m, mutant_name, result in mutants]

    for time, key in sorted(times_and_keys):
        if not time:
            print("<no tests>", key)
        else:
            print(f"{int(time * 1000)}ms", key)


@cli.command()
@click.argument("mutant_name", required=True, nargs=1)
def tests_for_mutant(mutant_name: str) -> None:
    if not load_stats():
        print("Failed to load stats. Please run mutmut first to collect stats.")
        exit(1)

    tests = tests_for_mutant_names([mutant_name])
    for test in sorted(tests):
        print(test)


def stop_all_children(mutants: list[tuple[SourceFileMutationData, str, int | None]]) -> None:
    for m, _, _ in mutants:
        m.stop_children()


# Guard against "context has already been set" when mutmut.__main__ is
# re-executed (see GH-466).
if get_start_method(allow_none=True) is None:
    set_start_method("fork")
elif "mutmut.__main__" not in sys.modules:
    warnings.warn(
        "mutmut.__main__ was re-executed because it was not cached in "
        "sys.modules. Use `mutmut run` instead of `python -m mutmut run` "
        "to avoid this.",
        stacklevel=1,
    )


@cli.command()
@click.option("--max-children", type=int)
@click.argument("mutant_names", required=False, nargs=-1)
def run(mutant_names: tuple[str, ...] | list[str], *, max_children: int | None) -> None:
    assert isinstance(mutant_names, (tuple, list)), mutant_names
    _run(mutant_names, max_children)


# separate function, so we can call it directly from the tests
def _run(mutant_names: tuple[str, ...] | list[str], max_children: int | None) -> None:
    # TODO: run no-ops once in a while to detect if we get false negatives
    # TODO: we should be able to get information on which tests killed mutants, which means we can get a list of tests and how many mutants each test kills. Those that kill zero mutants are redundant!
    os.environ["MUTANT_UNDER_TEST"] = "mutant_generation"
    Config.ensure_loaded()

    if max_children is None:
        max_children = os.cpu_count() or 4

    start = datetime.now()
    makedirs(Path("mutants"), exist_ok=True)
    with CatchOutput(spinner_title="Generating mutants"):
        copy_src_dir()
        copy_also_copy_files()
        setup_source_paths()
        store_lines_covered_by_tests()
        stats = create_mutants(max_children)

    time = datetime.now() - start
    print(
        f"    done in {round(time.total_seconds() * 1000)}ms ({stats.mutated} files mutated, {stats.ignored} ignored, {stats.unmodified} unmodified)",
    )

    mutants_caught_by_type_checker: dict[str, FailedTypeCheckMutant] = {}
    if Config.get().type_check_command:
        with CatchOutput(spinner_title="Filtering mutations with type checker"):
            mutants_caught_by_type_checker = filter_mutants_with_type_checker()

    # TODO: config/option for runner
    # runner = HammettRunner()
    runner = PytestRunner()
    runner.prepare_main_test_run()

    # TODO: run these steps only if we have mutants to test

    collect_or_load_stats(
        runner,
        mutants_caught_by_type_checker=mutants_caught_by_type_checker,
        apply_config_invalidation=True,
    )

    mutants, source_file_mutation_data_by_path = collect_source_file_mutation_data(mutant_names=mutant_names)

    _check_test_to_mutant_associations(source_file_mutation_data_by_path)

    os.environ["MUTANT_UNDER_TEST"] = ""
    with CatchOutput(spinner_title="Running clean tests") as output_catcher:
        tests = tests_for_mutant_names(mutant_names)

        clean_test_exit_code = runner.run_tests(mutant_name=None, tests=tests)
        if clean_test_exit_code != 0:
            output_catcher.dump_output()
            print("Failed to run clean test")
            exit(1)
    print("    done")

    # this can't be the first thing, because it can fail deep inside pytest/django setup and then everything is destroyed
    run_forced_fail_test(runner)

    runner.prepare_main_test_run()

    def read_one_child_exit_status() -> None:
        pid, wait_status = os.wait()
        exit_code = os.waitstatus_to_exitcode(wait_status)
        if Config.get().debug:
            print("    worker exit code", exit_code)
        source_file_mutation_data_by_pid[pid].register_result(pid=pid, exit_code=exit_code)

    source_file_mutation_data_by_pid: dict[int, SourceFileMutationData] = {}  # many pids map to one MutationData
    running_children = 0
    count_tried = 0

    # Run estimated fast mutants first, calculated as the estimated time for a surviving mutant.
    mutants = sorted(mutants, key=lambda x: estimated_worst_case_time(x[1]))
    start = datetime.now()
    try:
        gc.freeze()
        print("Running mutation testing")

        # Now do mutation
        for mutation_data, mutant_name, result in mutants:
            mutant_name = mutant_name.replace("__init__.", "")
            tests = mutmut.tests_by_mangled_function_name.get(mangled_name_from_mutant_name(mutant_name), set())
            estimated_time_of_tests = sum(mutmut.duration_by_test[test_name] for test_name in tests)
            mutation_data.estimated_time_of_tests_by_mutant[mutant_name] = estimated_time_of_tests
            print_stats(source_file_mutation_data_by_path)

            # Rerun mutant if it's explicitly mentioned, but otherwise let the result stand
            if not mutant_names and result is not None:
                continue

            if not tests:
                mutation_data.exit_code_by_key[mutant_name] = 33
                mutation_data.save()
                continue

            failed_type_check_mutant = mutants_caught_by_type_checker.get(mutant_name)
            if failed_type_check_mutant:
                mutation_data.exit_code_by_key[mutant_name] = 37
                mutation_data.type_check_error_by_key[mutant_name] = failed_type_check_mutant.error.error_description
                mutation_data.save()
                continue

            config = Config.get()
            pid = os.fork()
            if pid == 0:
                # In the child
                os.environ["MUTANT_UNDER_TEST"] = mutant_name
                setproctitle(f"mutmut: {mutant_name}")

                # Run fast tests first
                sorted_tests = sorted(tests, key=lambda test_name: mutmut.duration_by_test[test_name])
                if not sorted_tests:
                    os._exit(33)

                cpu_time_limit_s = ceil(
                    (estimated_time_of_tests + config.timeout_constant) * config.timeout_multiplier * 2 + process_time()
                )
                # signal SIGXCPU after <cpu_time_limit>. One second later signal SIGKILL if it is still running
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_time_limit_s, cpu_time_limit_s + 1))

                with CatchOutput():
                    result = runner.run_tests(mutant_name=mutant_name, tests=sorted_tests)

                if result != 0:
                    pass
                os._exit(result)
            else:
                # in the parent
                wall_time_limit_s = (estimated_time_of_tests + config.timeout_constant) * config.timeout_multiplier
                register_timeout(pid=pid, timeout_s=wall_time_limit_s)
                source_file_mutation_data_by_pid[pid] = mutation_data
                mutation_data.register_pid(pid=pid, key=mutant_name)
                running_children += 1

            if running_children >= max_children:
                read_one_child_exit_status()
                count_tried += 1
                running_children -= 1

        try:
            while running_children:
                read_one_child_exit_status()
                count_tried += 1
                running_children -= 1
        except ChildProcessError:
            pass
    except KeyboardInterrupt:
        print("Stopping...")
        stop_all_children(mutants)
    finally:
        gc.unfreeze()

    elapsed_time = datetime.now() - start

    print_stats(source_file_mutation_data_by_path, force_output=True)
    print()
    print(f"{count_tried / elapsed_time.total_seconds():.2f} mutations/second")

    if mutant_names:
        print()
        print("Mutant results")
        print("--------------")
        exit_code_by_key = {}
        # If the user gave a specific list of mutants, print result for these specifically
        for m, mutant_name, result in mutants:
            exit_code_by_key[mutant_name] = m.exit_code_by_key[mutant_name]

        for mutant_name, exit_code in sorted(exit_code_by_key.items()):
            print(emoji_by_status.get(status_by_exit_code[exit_code], "?"), mutant_name)

        print()


def tests_for_mutant_names(mutant_names: tuple[str, ...] | list[str]) -> set[str]:
    tests = set()
    for mutant_name in mutant_names:
        if "*" in mutant_name:
            for name, tests_of_this_name in mutmut.tests_by_mangled_function_name.items():
                if fnmatch.fnmatch(name, mutant_name):
                    tests |= set(tests_of_this_name)
        else:
            tests |= set(mutmut.tests_by_mangled_function_name[mangled_name_from_mutant_name(mutant_name)])
    return tests


@cli.command()
@click.option("--all", default=False)
def results(all: bool) -> None:
    Config.ensure_loaded()
    for path in walk_mutatable_files():
        m = SourceFileMutationData(path=path)
        m.load()
        for k, v in m.exit_code_by_key.items():
            status = status_by_exit_code[v]
            if status == "killed" and not all:
                continue
            print(f"    {k}: {status}")


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


def get_diff_for_mutant(
    mutant_name: str,
    source: str | None = None,
    path: Path | str | None = None,
) -> str:
    if path is None:
        m = find_mutant(mutant_name)
        path = m.path
        status = status_by_exit_code[m.exit_code_by_key[mutant_name]]
    else:
        status = "not checked"

    print(f"# {mutant_name}: {status}")

    if source is None:
        module = read_mutants_module(path)
    else:
        module = cst.parse_module(source)
    orig_code = cst.Module([read_original_function(module, mutant_name)]).code.strip()
    mutant_code = cst.Module([read_mutant_function(module, mutant_name)]).code.strip()

    path_str = str(path)
    return "\n".join(
        [
            line
            for line in unified_diff(
                orig_code.split("\n"), mutant_code.split("\n"), fromfile=path_str, tofile=path_str, lineterm=""
            )
        ]
    )


@cli.command()
@click.argument("mutant_name")
def show(mutant_name: str) -> None:
    Config.ensure_loaded()
    print(get_diff_for_mutant(mutant_name))
    return


@cli.command()
@click.argument("mutant_name")
def apply(mutant_name: str) -> None:
    # try:
    Config.ensure_loaded()
    apply_mutant(mutant_name)
    # except FileNotFoundError as e:
    #     print(e)


def apply_mutant(mutant_name: str) -> None:
    path = find_mutant(mutant_name).path

    orig_function_name, class_name = orig_function_and_class_names_from_key(mutant_name)
    orig_function_name = orig_function_name.rpartition(".")[-1]

    orig_module = read_orig_module(path)
    mutants_module = read_mutants_module(path)

    mutant_function = read_mutant_function(mutants_module, mutant_name)
    mutant_function = mutant_function.with_changes(name=cst.Name(orig_function_name))

    original_function = find_top_level_function_or_method(orig_module, orig_function_name)
    if not original_function:
        raise FileNotFoundError(f"Could not apply mutant {mutant_name}")

    new_module: cst.Module = orig_module.deep_replace(original_function, mutant_function)  # type: ignore[arg-type]

    with open(path, "w") as f:
        f.write(new_module.code)


@cli.command()
@click.option("--show-killed", is_flag=True, default=False, help="Display mutants killed by tests and type checker.")
def browse(show_killed: bool) -> None:
    Config.ensure_loaded()

    from rich.syntax import Syntax
    from textual.app import App
    from textual.containers import Container
    from textual.widget import Widget
    from textual.widgets import DataTable
    from textual.widgets import Footer
    from textual.widgets import Static

    class ResultBrowser(App[None]):
        loading_id = None
        CSS_PATH = "result_browser_layout.tcss"
        BINDINGS = [
            ("q", "quit()", "Quit"),
            ("r", "retest_mutant()", "Retest mutant"),
            ("f", "retest_function()", "Retest function"),
            ("m", "retest_module()", "Retest module"),
            ("a", "apply_mutant()", "Apply mutant to disk"),
            ("t", "view_tests()", "View tests for mutant"),
        ]

        columns = [
            ("path", "Path"),
        ] + [(status, Text(emoji, justify="right")) for status, emoji in emoji_by_status.items()]

        cursor_type = "row"
        source_file_mutation_data_and_stat_by_path: dict[str, tuple[SourceFileMutationData, Stat]] = {}
        path_by_name: dict[str, Path] = {}

        def compose(self) -> Iterable[Any]:
            with Container(classes="container"):
                yield DataTable(id="files")
                yield DataTable(id="mutants")
            with Widget(id="diff_view_widget"):
                yield Static(id="description")
                yield Static(id="diff_view")
            yield Footer()

        def on_mount(self) -> None:
            # noinspection PyTypeChecker
            files_table: DataTable[Any] = self.query_one("#files")  # type: ignore[assignment]
            files_table.cursor_type = "row"
            for key, label in self.columns:
                files_table.add_column(key=key, label=label)

            # noinspection PyTypeChecker
            mutants_table: DataTable[Any] = self.query_one("#mutants")  # type: ignore[assignment]
            mutants_table.cursor_type = "row"
            mutants_table.add_columns("name", "status")

            self.read_data()
            self.populate_files_table()

        def read_data(self) -> None:
            Config.ensure_loaded()
            self.source_file_mutation_data_and_stat_by_path = {}
            self.path_by_name: dict[str, Path] = {}

            for p in walk_mutatable_files():
                source_file_mutation_data = SourceFileMutationData(path=p)
                source_file_mutation_data.load()
                stat = collect_stat(source_file_mutation_data)

                self.source_file_mutation_data_and_stat_by_path[str(p)] = source_file_mutation_data, stat
                for name in source_file_mutation_data.exit_code_by_key:
                    self.path_by_name[name] = p

        def populate_files_table(self) -> None:
            # noinspection PyTypeChecker
            files_table: DataTable[Any] = self.query_one("#files")  # type: ignore[assignment]
            # TODO: restore selection
            selected_row = files_table.cursor_row
            files_table.clear()

            for p, (source_file_mutation_data, stat) in sorted(self.source_file_mutation_data_and_stat_by_path.items()):
                row = [p] + [
                    Text(str(getattr(stat, k.replace(" ", "_"))), justify="right") for k, _ in self.columns[1:]
                ]
                files_table.add_row(*row, key=str(p))

            files_table.move_cursor(row=selected_row)

        def on_data_table_row_highlighted(self, event: Any) -> None:
            if not event.row_key or not event.row_key.value:
                return
            if event.data_table.id == "files":
                # noinspection PyTypeChecker
                mutants_table: DataTable[Any] = self.query_one("#mutants")  # type: ignore[assignment]
                mutants_table.clear()
                source_file_mutation_data, stat = self.source_file_mutation_data_and_stat_by_path[event.row_key.value]
                for k, v in source_file_mutation_data.exit_code_by_key.items():
                    status = status_by_exit_code[v]
                    if status not in ("killed", "caught by type check") or show_killed:
                        mutants_table.add_row(k, emoji_by_status[status], key=k)
            else:
                assert event.data_table.id == "mutants"
                # noinspection PyTypeChecker
                description_view: Static = self.query_one("#description")  # type: ignore[assignment]
                mutant_name = event.row_key.value
                self.loading_id = mutant_name
                path = self.path_by_name.get(mutant_name)
                source_file_mutation_data, stat = self.source_file_mutation_data_and_stat_by_path[str(path)]

                exit_code = source_file_mutation_data.exit_code_by_key[mutant_name]
                status = status_by_exit_code[exit_code]
                estimated_duration = source_file_mutation_data.estimated_time_of_tests_by_mutant.get(mutant_name, "?")
                duration = source_file_mutation_data.durations_by_key.get(mutant_name, "?")
                type_check_error = source_file_mutation_data.type_check_error_by_key.get(mutant_name, "?")

                view_tests_description = "(press t to view tests executed for this mutant)"

                match status:
                    case "killed":
                        description = f"Killed ({exit_code=}): Mutant caused a test to fail 🎉"
                    case "survived":
                        description = f"Survived ({exit_code=}): No test detected this mutant. {view_tests_description}"
                    case "skipped":
                        description = f"Skipped ({exit_code=})"
                    case "check was interrupted by user":
                        description = f"User interrupted ({exit_code=})"
                    case "caught by type check":
                        description = f"Caught by type checker ({exit_code=}): {type_check_error}"
                    case "timeout":
                        description = (
                            f"Timeout ({exit_code=}): Timed out because tests did not finish within {duration:.3f} seconds. "
                            f"Tests without mutation took {estimated_duration:.3f} seconds. {view_tests_description}"
                        )
                    case "no tests":
                        description = (
                            f"Untested ({exit_code=}): Skipped because selected tests do not execute this code."
                        )
                    case "segfault":
                        description = f"Segfault ({exit_code=}): Running pytest with this mutant segfaulted."
                    case "suspicious":
                        description = (
                            f"Unknown ({exit_code=}): Running pytest with this mutant resulted in an unknown exit code."
                        )
                    case "not checked":
                        description = "Not checked in the last mutmut run."
                    case _:
                        description = f"Unknown status ({exit_code=}, {status=})"
                description_view.update(f"\n {description}\n")

                diff_view: Static = self.query_one("#diff_view")  # type: ignore[assignment]
                diff_view.update("<loading code diff...>")

                def load_thread() -> None:
                    Config.ensure_loaded()
                    try:
                        d = get_diff_for_mutant(event.row_key.value, path=path)
                        if event.row_key.value == self.loading_id:
                            diff_view.update(Syntax(d, "diff"))
                    except Exception as e:
                        diff_view.update(f"<{type(e)} {e}>")

                t = Thread(target=load_thread)
                t.start()

        def retest(self, pattern: str | None) -> None:
            if pattern is None:
                return
            self._run_subprocess_command("run", [pattern])

        def view_tests(self, mutant_name: str | None) -> None:
            if mutant_name is None:
                return
            self._run_subprocess_command("tests-for-mutant", [mutant_name])

        def _run_subprocess_command(self, command: str, args: list[str]) -> None:
            with self.suspend():
                browse_index = sys.argv.index("browse")
                initial_args = sys.argv[:browse_index]
                subprocess_args = [sys.executable, *initial_args, command, *args]
                print(">", *subprocess_args)
                subprocess.run(subprocess_args)
                input("press enter to return to browser")

            self.read_data()
            self.populate_files_table()

        def get_mutant_name_from_selection(self) -> str | None:
            # noinspection PyTypeChecker
            mutants_table: DataTable[Any] = self.query_one("#mutants")  # type: ignore[assignment]
            if mutants_table.cursor_row is None or not mutants_table.is_valid_row_index(mutants_table.cursor_row):
                return None

            result: str = mutants_table.get_row_at(mutants_table.cursor_row)[0]
            return result

        def action_retest_mutant(self) -> None:
            self.retest(self.get_mutant_name_from_selection())

        def action_retest_function(self) -> None:
            name = self.get_mutant_name_from_selection()
            if name is not None:
                self.retest(name.rpartition("__mutmut_")[0] + "__mutmut_*")

        def action_retest_module(self) -> None:
            name = self.get_mutant_name_from_selection()
            if name is not None:
                self.retest(name.rpartition(".")[0] + ".*")

        def action_apply_mutant(self) -> None:
            Config.ensure_loaded()
            # noinspection PyTypeChecker
            mutants_table: DataTable[Any] = self.query_one("#mutants")  # type: ignore[assignment]
            if mutants_table.cursor_row is None or not mutants_table.is_valid_row_index(mutants_table.cursor_row):
                return
            apply_mutant(mutants_table.get_row_at(mutants_table.cursor_row)[0])

        def action_view_tests(self) -> None:
            name = self.get_mutant_name_from_selection()
            if name is not None:
                self.view_tests(name)

    ResultBrowser().run()


if __name__ == "__main__":
    cli()
