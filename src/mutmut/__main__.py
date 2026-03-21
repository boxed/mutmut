from __future__ import annotations

import io
import os
import platform
import sys
from collections.abc import Iterable

from mutmut.stats import calculate_summary_stats
from mutmut.stats import load_stats
from mutmut.stats import print_stats
from mutmut.stats import save_stats

if platform.system() == "Windows":
    print(
        "To run mutmut on Windows, please use the WSL. Native windows support is tracked in issue https://github.com/boxed/mutmut/issues/397"
    )
    sys.exit(1)

import ast
import fnmatch
import json
import shutil
import warnings
from collections.abc import Sequence
from datetime import datetime
from difflib import unified_diff
from math import ceil
from multiprocessing import Pool
from multiprocessing import get_start_method
from multiprocessing import set_start_method
from os import makedirs
from pathlib import Path
from time import process_time

import click
import libcst as cst

from mutmut.code_coverage import gather_coverage
from mutmut.code_coverage import get_covered_lines_for_file
from mutmut.configuration import ProcessIsolation
from mutmut.configuration import config
from mutmut.core import MutmutProgrammaticFailException
from mutmut.models.mutant_status import MutantStatus
from mutmut.models.mutation import MutationMetadata
from mutmut.models.results import FileMutationResult
from mutmut.models.results import MutantGenerationStats
from mutmut.models.source_file_mutation_data import SourceFileMutationData
from mutmut.mutation.file_mutation import filter_mutants_with_type_checker
from mutmut.mutation.file_mutation import mutate_file_contents
from mutmut.runners.harness import CollectTestsFailedException
from mutmut.runners.harness import PytestRunner
from mutmut.runners.harness import collected_test_names
from mutmut.runners.harness import strip_prefix
from mutmut.state import state
from mutmut.stats import write_summary_file
from mutmut.ui.terminal import SpinnerTask
from mutmut.utils.file_utils import copy_also_copy_files
from mutmut.utils.file_utils import copy_src_dir
from mutmut.utils.file_utils import setup_source_paths
from mutmut.utils.file_utils import walk_mutatable_files
from mutmut.utils.file_utils import walk_source_files
from mutmut.utils.format_utils import get_module_from_key
from mutmut.utils.format_utils import mangled_name_from_mutant_name
from mutmut.utils.format_utils import orig_function_and_class_names_from_key
from mutmut.utils.logging_utils import get_logger
from mutmut.utils.logging_utils import setup_file_logging
from mutmut.workers.isolation import MutantResult
from mutmut.workers.isolation import MutantRunner
from mutmut.workers.isolation import get_mutant_runner

# Document: surviving mutants are retested when you ask mutmut to retest them, interactively in the UI or via command line


# TODO: pragma no mutate should end up in `skipped` category

logger = get_logger("mutmut.main")


class InvalidGeneratedSyntaxException(Exception):
    def __init__(self, file: Path | str) -> None:
        super().__init__(
            f"Mutmut generated invalid python syntax for {file}. "
            "If the original file has valid python syntax, please file an issue "
            "with a minimal reproducible example file."
        )


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

        if config().should_mutate(path):
            return create_mutants_for_file(path, output_path)
        else:
            shutil.copy(path, output_path)
            return FileMutationResult(ignored=True)
    except Exception as e:
        return FileMutationResult(error=e)


def store_lines_covered_by_tests() -> None:
    if config().mutate_only_covered_lines:
        state()._covered_lines = gather_coverage(PytestRunner(), list(walk_source_files()))


def create_mutants_for_file(source_path: Path, output_path: Path) -> FileMutationResult:
    warnings: list[Warning] = []

    try:
        source_mtime = os.path.getmtime(source_path)
        mutant_mtime = os.path.getmtime(output_path)
        # If the source is older than the mutant output, it hasn't been touched
        # since we last generated mutants — skip the expensive regeneration.
        if source_mtime < mutant_mtime:
            return FileMutationResult(unmodified=True)
    except OSError:
        pass

    with open(source_path) as f:
        source = f.read()

    with open(output_path, "w") as out:
        try:
            mutant_names, hash_by_function_name, metadata_by_name = write_all_mutants_to_file(
                out=out, source=source, filename=source_path
            )
        except cst.ParserSyntaxError as e:
            # if libcst cannot parse it, then copy the source without any mutations
            warnings.append(SyntaxWarning(f"Unsupported syntax in {source_path} ({str(e)}), skipping"))
            out.write(source)
            mutant_names, hash_by_function_name, metadata_by_name = [], {}, {}

    # validate no syntax errors of mutants
    with open(output_path) as f:
        try:
            ast.parse(f.read())
        except (IndentationError, SyntaxError) as e:
            invalid_syntax_error = InvalidGeneratedSyntaxException(output_path)
            invalid_syntax_error.__cause__ = e
            return FileMutationResult(warnings=warnings, error=invalid_syntax_error)

    source_file_mutation_data = SourceFileMutationData(path=source_path)
    source_file_mutation_data.load()
    module_name = strip_prefix(str(source_path)[: -len(source_path.suffix)].replace(os.sep, "."), prefix="src.")

    old_hashes = source_file_mutation_data.hash_by_function_name

    changed_functions_local = {
        func_name for func_name, new_hash in hash_by_function_name.items() if old_hashes.get(func_name) != new_hash
    }

    new_keys = {".".join([module_name, x]).replace(".__init__.", "."): None for x in mutant_names}

    # Merge: keep existing results for mutants that still exist, add None for new ones
    # BUT: if the function's hash changed, reset the mutant to None (needs re-testing)
    merged_exit_codes: dict[str, int | None] = {}
    for key in new_keys:
        mangled_func = mangled_name_from_mutant_name(key)
        # Extract just the function key (e.g., "x_add") for comparison with hash_by_function_name keys
        _, _, func_name = mangled_func.rpartition(".")

        if func_name in changed_functions_local:
            merged_exit_codes[key] = None
        elif key in source_file_mutation_data.exit_code_by_key:
            merged_exit_codes[key] = source_file_mutation_data.exit_code_by_key[key]
        else:
            merged_exit_codes[key] = None

    source_file_mutation_data.exit_code_by_key = merged_exit_codes
    source_file_mutation_data.hash_by_function_name = hash_by_function_name
    assert None not in hash_by_function_name

    # Build fully-qualified function names for return to parent
    # Keys are fully qualified: foo.bar.x_baz
    current_hashes_qualified: dict[str, str] = {}
    for mangled_name, hash_value in hash_by_function_name.items():
        full_name = f"{module_name}.{mangled_name}".replace(".__init__.", ".")
        current_hashes_qualified[full_name] = hash_value

    # Build fully-qualified changed function names for return to parent
    changed_functions_qualified = {
        f"{module_name}.{func_name}".replace(".__init__.", ".") for func_name in changed_functions_local
    }

    # Build metadata with full module-qualified keys
    source_file_mutation_data.mutation_metadata_by_module_name = {
        ".".join([module_name, k]).replace(".__init__.", "."): v for k, v in metadata_by_name.items()
    }

    source_file_mutation_data.save()

    return FileMutationResult(
        warnings=warnings,
        changed_functions=changed_functions_qualified,
        current_hashes=current_hashes_qualified,
    )


def write_all_mutants_to_file(
    *, out: io.TextIOWrapper, source: str, filename: Path
) -> tuple[Sequence[str], dict[str, str], dict[str, MutationMetadata]]:
    filename_str = str(filename)
    mutated_code, mutant_names, hash_by_function_name, metadata_by_name = mutate_file_contents(
        filename_str, source, get_covered_lines_for_file(filename_str, state()._covered_lines)
    )
    out.write(mutated_code)

    return mutant_names, hash_by_function_name, metadata_by_name


def run_forced_fail_test(runner: MutantRunner) -> None:
    os.environ["MUTANT_UNDER_TEST"] = "fail"
    with SpinnerTask("Running forced fail test", debug=config().debug) as task:
        try:
            if runner.run_forced_fail() == 0:
                task.dump_output()
                print("FAILED: Unable to force test failures")
                raise SystemExit(1)
        except MutmutProgrammaticFailException:
            pass
    os.environ["MUTANT_UNDER_TEST"] = ""


@click.group()
@click.version_option()
def cli() -> None:
    pass


def run_stats_collection(runner: MutantRunner, tests: Iterable[str] | None = None) -> None:
    if tests is None:
        tests = set()  # Meaning all...

    os.environ["MUTANT_UNDER_TEST"] = "stats"
    os.environ["PY_IGNORE_IMPORTMISMATCH"] = "1"
    start_cpu_time = process_time()

    with SpinnerTask("Running stats", debug=config().debug) as task:
        collect_stats_exit_code = runner.collect_stats(tests=tests)
        if collect_stats_exit_code != 0:
            task.dump_output()
            print(f"failed to collect stats. runner returned {collect_stats_exit_code}")
            exit(1)
        # ensure that at least one mutant has associated tests
        num_associated_tests = sum(len(tests) for tests in state().tests_by_mangled_function_name.values())
        if num_associated_tests == 0:
            task.dump_output()
            print(
                "Stopping early, because we could not find any test case for any mutant. It seems that the selected tests do not cover any code that we mutated."
            )
            if not config().debug:
                print("You can set debug=true to see the executed test names in the output above.")
            else:
                print("In the last pytest run above, you can see which tests we executed.")
            print("You can use mutmut browse to check which parts of the source code we mutated.")
            print(
                "If some of the mutated code should be covered by the executed tests, consider opening an issue (with a MRE if possible)."
            )
            exit(1)

    if not tests:  # again, meaning all
        state().stats_time = process_time() - start_cpu_time

    if not collected_test_names():
        print("failed to collect stats, no active tests found")
        exit(1)

    save_stats()


def collect_or_load_stats(runner: MutantRunner, invalidate_stale_callers: bool = True) -> None:
    did_load = load_stats()

    if not did_load:
        # Run full stats
        run_stats_collection(runner)
    else:
        # Clean up stats for deleted source files
        _cleanup_stale_stats()

        if config().track_dependencies and invalidate_stale_callers:
            _invalidate_stale_dependency_edges()

        # Save to persist the cleanup
        save_stats()

        # Run incremental stats
        with SpinnerTask("Listing all tests", debug=config().debug) as task:
            os.environ["MUTANT_UNDER_TEST"] = "list_all_tests"
            try:
                all_tests_result = runner.list_all_tests()
            except CollectTestsFailedException:
                task.dump_output()
                print("Failed to collect list of tests")
                exit(1)

        all_tests_result.clear_out_obsolete_test_names()

        new_tests = all_tests_result.new_tests()

        if new_tests:
            print(f"Found {len(new_tests)} new tests, rerunning stats collection")
            run_stats_collection(runner, tests=new_tests)


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
                caught_by_type_check=s.caught_by_type_check,
            ),
            f,
            indent=4,
        )


# exports CI/CD stats to block pull requests from merging if mutation score is too low, or used in other ways in CI/CD pipelines
@cli.command()
def export_cicd_stats() -> None:
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
) -> tuple[list[tuple[SourceFileMutationData, str, int | None]], dict[str, SourceFileMutationData]]:
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


def estimated_worst_case_time(mutant_name: str) -> float:
    tests = state().tests_by_mangled_function_name.get(mangled_name_from_mutant_name(mutant_name), set())
    return sum(state().duration_by_test[t] for t in tests)


@cli.command()
@click.argument("mutant_names", required=False, nargs=-1)
def print_time_estimates(mutant_names: tuple[str, ...]) -> None:
    assert isinstance(mutant_names, tuple | list), mutant_names

    runner = get_mutant_runner()

    collect_or_load_stats(runner)

    mutants, source_file_mutation_data_by_path = collect_source_file_mutation_data(mutant_names=mutant_names)

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
@click.option("-f", "--fresh", is_flag=True, help="Force a fresh run, removing the /mutants directory")
@click.argument("mutant_names", required=False, nargs=-1)
def run(mutant_names: tuple[str, ...], *, max_children: int | None, fresh: bool = False) -> None:
    assert isinstance(mutant_names, tuple | list), mutant_names
    _run(mutant_names, max_children, fresh)


# separate function, so we can call it directly from the tests
def _run(mutant_names: tuple[str, ...] | list[str], max_children: int | None, fresh: bool = False) -> None:
    # TODO: run no-ops once in a while to detect if we get false negatives
    # TODO: we should be able to get information on which tests killed mutants, which means we can get a list of tests and how many mutants each test kills. Those that kill zero mutants are redundant!
    os.environ["MUTANT_UNDER_TEST"] = "mutant_generation"

    if fresh:
        shutil.rmtree("mutants", ignore_errors=True)

    if config().log_to_file or config().debug:
        setup_file_logging()
    logger.info("Starting mutation testing run")
    logger.info("mutant_names=%s, max_children=%s", mutant_names, max_children)
    logger.info("process_isolation=%s", config().process_isolation)
    logger.info("hot_fork_warmup=%s", config().hot_fork_warmup)

    if max_children is None:
        max_children = os.cpu_count() or 4

    logger.info("Using %d workers", max_children)

    makedirs(Path("mutants"), exist_ok=True)
    with SpinnerTask("Generating mutants", debug=config().debug) as task:
        copy_src_dir()
        copy_also_copy_files()
        setup_source_paths()
        store_lines_covered_by_tests()
        stats = create_mutants(max_children)

    state().mutant_generation_time = task.elapsed_seconds
    logger.info("Mutant generation completed in %.2f seconds", state().mutant_generation_time)

    if config().type_check_command:
        with SpinnerTask("Filtering mutations with type checker", debug=config().debug):
            mutants_caught_by_type_checker = filter_mutants_with_type_checker()
    else:
        mutants_caught_by_type_checker = {}

    mutation_runner: MutantRunner = get_mutant_runner(max_children)

    # TODO: run these steps only if we have mutants to test

    collect_or_load_stats(mutation_runner)

    mutants, source_file_mutation_data_by_path = collect_source_file_mutation_data(mutant_names=mutant_names)
    logger.info("Collected %d mutants from %d source files", len(mutants), len(source_file_mutation_data_by_path))

    os.environ["MUTANT_UNDER_TEST"] = ""
    logger.info("Running clean tests")
    with SpinnerTask("Running clean tests", debug=config().debug) as task:
        tests = tests_for_mutant_names(mutant_names)

        clean_test_exit_code = mutation_runner.run_clean_tests(tests=tests)
        if clean_test_exit_code != 0:
            task.dump_output()
            logger.error("Clean test failed with exit code %d", clean_test_exit_code)
            print("Failed to run clean test")
            exit(1)
    state().clean_tests_time = task.elapsed_seconds
    logger.info("Clean tests passed")

    # this can't be the first thing, because it can fail deep inside pytest/django setup and then everything is destroyed
    forced_fail_start = datetime.now()
    run_forced_fail_test(mutation_runner)
    state().forced_fail_time = (datetime.now() - forced_fail_start).total_seconds()

    # Build a map from mutant_name to mutation_data for result registration
    mutation_data_by_mutant_name: dict[str, SourceFileMutationData] = {}
    count_tried = 0

    # Run estimated fast mutants first, calculated as the estimated time for a surviving mutant.
    mutants = sorted(mutants, key=lambda x: estimated_worst_case_time(x[1]))
    mutation_test_start = datetime.now()

    # Start the mutation runner
    logger.info(
        "Created %s with %d workers (mutants_to_run=%d)",
        type(mutation_runner).__name__,
        max_children,
        len(mutants),
    )
    mutation_runner.startup()
    logger.info("Runner started")
    try:
        print("Running mutation testing")

        # Now do mutation
        for mutation_data, mutant_name, result in mutants:
            # Rerun mutant if it's explicitly mentioned, but otherwise let the result stand
            if not mutant_names and result is not None:
                continue

            mutant_name = mutant_name.replace("__init__.", "")
            tests = state().tests_by_mangled_function_name.get(mangled_name_from_mutant_name(mutant_name), set())
            estimated_time_of_tests = sum(state().duration_by_test[test_name] for test_name in tests)
            mutation_data.estimated_time_of_tests_by_mutant[mutant_name] = estimated_time_of_tests
            print_stats(source_file_mutation_data_by_path)

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

            # Store mapping for result registration
            mutation_data_by_mutant_name[mutant_name] = mutation_data

            # Wait for capacity before submitting
            while not mutation_runner.has_capacity():
                mutation_result = mutation_runner.wait_for_result()
                logger.debug(f"worker exit code {mutation_result.exit_code}")
                if config().debug:
                    print("    worker exit code", mutation_result.exit_code)
                _register_mutant_result(mutation_result, mutation_data_by_mutant_name)
                count_tried += 1

            tests_to_run = list(tests)
            if config().process_isolation == ProcessIsolation.FORK:
                # Run fast tests first for fork runner; hot-fork keeps input order.
                tests_to_run = sorted(tests_to_run, key=lambda test_name: state().duration_by_test[test_name])
            cpu_time_limit_s = ceil((estimated_time_of_tests + 1) * 30)

            mutation_runner.submit(mutant_name, tests_to_run, cpu_time_limit_s, estimated_time_of_tests)

        mutation_runner.signal_work_complete()

        while mutation_runner.pending_count() > 0:
            try:
                mutation_result = mutation_runner.wait_for_result()
                logger.debug(f"worker exit code {mutation_result.exit_code}")
                if config().debug:
                    print("    worker exit code", mutation_result.exit_code)
                _register_mutant_result(mutation_result, mutation_data_by_mutant_name)
                count_tried += 1
            except ChildProcessError:
                break

    except KeyboardInterrupt:
        print("Stopping...")
        stop_all_children(mutants)
    finally:
        mutation_runner.shutdown()

    mutation_test_time = datetime.now() - mutation_test_start
    state().mutation_testing_time = mutation_test_time.total_seconds()

    print_stats(source_file_mutation_data_by_path, force_output=True)
    print()
    print(f"{count_tried / mutation_test_time.total_seconds():.2f} mutations/second")

    # Calculate count_unchanged: mutants that were skipped because they already had results
    count_unchanged = sum(1 for _, _, result in mutants if result is not None and not mutant_names)

    # Write summary file for programmatic consumption
    summary_stats = calculate_summary_stats(source_file_mutation_data_by_path)
    write_summary_file(
        source_file_mutation_data_by_path,
        summary_stats,
        mutation_test_time.total_seconds(),
        count_unchanged,
    )

    if mutant_names:
        print()
        print("Mutant results")
        print("--------------")
        exit_code_by_key = {}
        # If the user gave a specific list of mutants, print result for these specifically
        for m, mutant_name, result in mutants:
            exit_code_by_key[mutant_name] = m.exit_code_by_key[mutant_name]

        for mutant_name, exit_code in sorted(exit_code_by_key.items()):
            status = MutantStatus.from_exit_code(exit_code)
            print(status.emoji, mutant_name)

        print()


def tests_for_mutant_names(mutant_names: tuple[str, ...] | list[str]) -> set[str]:
    tests = set()
    for mutant_name in mutant_names:
        if "*" in mutant_name:
            for (
                name,
                tests_of_this_name,
            ) in state().tests_by_mangled_function_name.items():
                if fnmatch.fnmatch(name, mutant_name):
                    tests |= set(tests_of_this_name)
        else:
            tests |= set(state().tests_by_mangled_function_name[mangled_name_from_mutant_name(mutant_name)])
    return tests


def _register_mutant_result(result: MutantResult, mutation_data_by_name: dict[str, SourceFileMutationData]) -> None:
    """Register a mutant test result.

    Args:
        result: The result from testing a mutant.
        mutation_data_by_name: Map from mutant name to its SourceFileMutationData.
    """
    mutation_data = mutation_data_by_name[result.mutant_name]
    mutation_data.exit_code_by_key[result.mutant_name] = result.exit_code
    mutation_data.save()


@cli.command()
@click.option("--all", default=False)
def results(all: bool) -> None:
    for path in walk_mutatable_files():
        m = SourceFileMutationData(path=path)
        m.load()
        for k, v in m.exit_code_by_key.items():
            status = MutantStatus.from_exit_code(v)
            if status is MutantStatus.KILLED and not all:
                continue
            print(f"    {k}: {status.text}")


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
        status = MutantStatus.from_exit_code(m.exit_code_by_key[mutant_name]).text
    else:
        status = MutantStatus.NOT_CHECKED.text

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


def _cleanup_stale_stats() -> None:
    """Remove stats entries for source files that no longer exist."""
    # Derive valid modules from current_function_hashes (populated during mutant generation)
    valid_modules = {get_module_from_key(key) for key in state().current_function_hashes}

    def _is_valid_key(key: str) -> bool:
        """Check if the key's module exists in current source files."""
        module = get_module_from_key(key)
        return module in valid_modules

    # Clean up tests_by_mangled_function_name - O(n) with set lookup
    stale_keys = [k for k in state().tests_by_mangled_function_name if not _is_valid_key(k)]
    for k in stale_keys:
        del state().tests_by_mangled_function_name[k]

    # Clean up function_dependencies (both keys and values)
    stale_dep_keys = [k for k in state().function_dependencies if not _is_valid_key(k)]
    for k in stale_dep_keys:
        del state().function_dependencies[k]

    # Also clean up stale callers in dependency values
    for _, callers in state().function_dependencies.items():
        stale_callers = {c for c in callers if not _is_valid_key(c)}
        callers -= stale_callers


def _invalidate_stale_dependency_edges() -> set[str]:
    """Remove changed functions from all caller sets in function_dependencies.

    When a function's code changes (hash differs), its outgoing call edges may
    have changed. We remove it from all callers_of[*] sets so stats collection
    can rebuild the correct edges.

    Returns the set of changed function names.
    """
    old_hashes = state().old_function_hashes
    new_hashes = state().current_function_hashes

    if not old_hashes:
        # First run or no previous stats - nothing to invalidate
        return set()

    # Find functions whose code changed (different hash) or were added/removed
    all_functions = old_hashes.keys() | new_hashes.keys()
    changed_functions = {f for f in all_functions if old_hashes.get(f) != new_hashes.get(f)}

    if not changed_functions:
        return set()

    # Remove changed functions from all caller sets
    # (their outgoing edges are now unknown/stale)
    for callers in state().function_dependencies.values():
        callers -= changed_functions

    # Also remove keys for deleted functions
    deleted_functions = old_hashes.keys() - new_hashes.keys()
    for f in deleted_functions:
        state().function_dependencies.pop(f, None)

    return changed_functions


@cli.command()
@click.argument("mutant_name")
def show(mutant_name: str) -> None:
    print(get_diff_for_mutant(mutant_name))
    return


@cli.command()
@click.argument("mutant_name")
def apply(mutant_name: str) -> None:
    # try:
    apply_mutant(mutant_name)
    # except FileNotFoundError as e:
    #     print(e)


def apply_mutant(mutant_name: str) -> None:
    path = find_mutant(mutant_name).path

    orig_function_name, _ = orig_function_and_class_names_from_key(mutant_name)
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
    from mutmut.ui.browse import run_result_browser

    run_result_browser(
        show_killed=show_killed,
        get_diff_for_mutant=get_diff_for_mutant,
        apply_mutant=apply_mutant,
    )


if __name__ == "__main__":
    cli()
