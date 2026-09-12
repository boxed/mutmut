from __future__ import annotations

import os
import platform
import sys
from collections.abc import Iterable
from typing import Any

from mutmut.state import state
from mutmut.utils.format_utils import get_module_from_key
from mutmut.utils.format_utils import get_mutant_name
from mutmut.utils.format_utils import mangled_name_from_mutant_name

if platform.system() == "Windows":
    print(
        "To run mutmut on Windows, please use the WSL. Native windows support is tracked in issue https://github.com/boxed/mutmut/issues/397"
    )
    sys.exit(1)
import ast
import fnmatch
import hashlib
import json
import shutil
import subprocess
import warnings
from collections.abc import Callable
from colorsys import hls_to_rgb
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from io import TextIOBase
from json import JSONDecodeError
from math import ceil
from multiprocessing import Pool
from multiprocessing import get_start_method
from multiprocessing import set_start_method
from os import makedirs
from pathlib import Path
from time import process_time
from types import TracebackType

import click
import libcst as cst

from mutmut.code_coverage import gather_coverage
from mutmut.code_coverage import get_covered_lines_for_file
from mutmut.code_coverage import get_excluded_lines_for_file
from mutmut.configuration import Config
from mutmut.configuration import config
from mutmut.core import MutmutProgrammaticFailException
from mutmut.mutation.data import MutantLineSpans
from mutmut.mutation.data import SourceFileMutationData
from mutmut.mutation.diff_apply import apply_mutant
from mutmut.mutation.diff_apply import find_mutant
from mutmut.mutation.diff_apply import get_diff_for_mutant
from mutmut.mutation.file_mutation import FailedTypeCheckMutant
from mutmut.mutation.file_mutation import MutatedFile
from mutmut.mutation.file_mutation import filter_mutants_with_type_checker
from mutmut.mutation.file_mutation import mutate_file_contents
from mutmut.mutation.trampoline import set_mutant_under_test
from mutmut.runners.harness import CollectTestsFailedException
from mutmut.runners.harness import PytestRunner
from mutmut.runners.harness import collected_test_names
from mutmut.stats import calculate_summary_stats
from mutmut.stats import emoji_by_status
from mutmut.stats import load_stats
from mutmut.stats import print_stats
from mutmut.stats import save_stats
from mutmut.stats import status_by_exit_code
from mutmut.ui.browse import run_result_browser
from mutmut.ui.terminal import print_status
from mutmut.utils.file_utils import copy_also_copy_files
from mutmut.utils.file_utils import copy_src_dir
from mutmut.utils.file_utils import setup_source_paths
from mutmut.utils.file_utils import walk_mutatable_files
from mutmut.utils.file_utils import walk_source_files
from mutmut.workers.isolation import MutantResult
from mutmut.workers.isolation import MutantRunner
from mutmut.workers.isolation import get_mutant_runner

# Document: surviving mutants are retested when you ask mutmut to retest them, interactively in the UI or via command line

# TODO: pragma no mutate should end up in `skipped` category


class InvalidGeneratedSyntaxException(Exception):
    def __init__(self, file: Path | str) -> None:
        super().__init__(
            f"Mutmut generated invalid python syntax for {file}. "
            "If the original file has valid python syntax, please file an issue "
            "with a minimal reproducible example file."
        )


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

        if config().should_mutate(path):
            return create_mutants_for_file(path, output_path)
        else:
            shutil.copy(path, output_path)
            return FileMutationResult(ignored=True)
    except Exception as e:
        return FileMutationResult(error=e)


def store_lines_covered_by_tests() -> None:
    if config().mutate_only_covered_lines:
        coverage_info = gather_coverage(PytestRunner(), list(walk_source_files()))
        state()._covered_lines = coverage_info.covered_lines
        state()._excluded_lines = coverage_info.excluded_lines


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
            mutated_file = write_all_mutants_to_file(out=out, source=source, filename=filename)
        except cst.ParserSyntaxError as e:
            # if libcst cannot parse it, then copy the source without any mutations
            warnings.append(SyntaxWarning(f"Unsupported syntax in {filename} ({str(e)}), skipping"))
            out.write(source)
            mutated_file = MutatedFile(
                code=source, mutant_names=[], line_span_by_function_name={}, hash_by_function_name={}
            )

    # validate no syntax errors of mutants
    with open(output_path) as f:
        try:
            ast.parse(f.read())
        except (IndentationError, SyntaxError) as e:
            invalid_syntax_error = InvalidGeneratedSyntaxException(output_path)
            invalid_syntax_error.__cause__ = e
            return FileMutationResult(warnings=warnings, error=invalid_syntax_error)

    hash_by_function_name = mutated_file.hash_by_function_name

    data = SourceFileMutationData(path=filename)
    data.load()
    old_hashes = data.hash_by_function_name
    changed = {f for f, h in hash_by_function_name.items() if old_hashes.get(f) != h}

    merged: dict[str, int | None] = {}
    for name in mutated_file.mutant_names:
        key = get_mutant_name(filename, name)
        func = mangled_name_from_mutant_name(key).rpartition(".")[2]
        if func not in hash_by_function_name or func in changed:
            merged[key] = None
        else:
            merged[key] = data.exit_code_by_key.get(key)
    data.exit_code_by_key = merged
    data.hash_by_function_name = dict(hash_by_function_name)
    data.save()

    MutantLineSpans(path=filename, span_by_function_name=mutated_file.line_span_by_function_name).save()

    current_hashes_qualified = {get_mutant_name(filename, func): h for func, h in hash_by_function_name.items()}
    changed_functions_qualified = {get_mutant_name(filename, func) for func in changed}

    return FileMutationResult(
        warnings=warnings,
        changed_functions=changed_functions_qualified,
        current_hashes=current_hashes_qualified,
    )


def write_all_mutants_to_file(*, out: TextIOBase, source: str, filename: Path) -> MutatedFile:
    mutated_file = mutate_file_contents(
        str(filename),
        source,
        get_covered_lines_for_file(str(filename), state()._covered_lines),
        get_excluded_lines_for_file(str(filename), state()._excluded_lines),
    )
    out.write(mutated_file.code)

    return mutated_file


def run_forced_fail_test(runner: MutantRunner) -> None:
    set_mutant_under_test("fail")
    with CatchOutput(spinner_title="Running forced fail test") as catcher:
        try:
            if runner.run_forced_fail() == 0:
                catcher.dump_output()
                print("FAILED: Unable to force test failures")
                raise SystemExit(1)
        except MutmutProgrammaticFailException:
            pass
    set_mutant_under_test("")
    print("    done")


class CatchOutput:
    def __init__(
        self,
        callback: Callable[[str], None] = lambda s: None,
        spinner_title: str | None = None,
    ) -> None:
        self.strings: list[str] = []
        self.spinner_title = spinner_title or ""
        if config().debug:
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
        if config().debug:
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


def run_stats_collection(runner: MutantRunner, tests: Iterable[str] | None = None) -> None:
    if tests is None:
        tests = []  # Meaning all...

    set_mutant_under_test("stats")
    os.environ["PY_IGNORE_IMPORTMISMATCH"] = "1"
    depth = config().dependency_tracking_depth
    os.environ["MUTMUT_DEPENDENCY_DEPTH"] = str(depth)
    start_cpu_time = process_time()

    with CatchOutput(spinner_title="Running stats") as output_catcher:
        collect_stats_exit_code = runner.collect_stats(tests)
        if collect_stats_exit_code != 0:
            output_catcher.dump_output()
            print(f"failed to collect stats. runner returned {collect_stats_exit_code}")
            exit(1)
        num_associated_tests = sum(len(tests) for tests in state().tests_by_mangled_function_name.values())
        if num_associated_tests == 0:
            output_catcher.dump_output()
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

    print("    done")
    if not tests:  # again, meaning all
        state().stats_time = process_time() - start_cpu_time

    if not collected_test_names():
        print("failed to collect stats, no active tests found")
        exit(1)

    save_stats()


def _cleanup_stale_stats() -> None:
    valid_modules = {get_module_from_key(key) for key in state().current_function_hashes}

    def _is_valid_key(key: str) -> bool:
        return get_module_from_key(key) in valid_modules

    stale_keys = [k for k in state().tests_by_mangled_function_name if not _is_valid_key(k)]
    for k in stale_keys:
        del state().tests_by_mangled_function_name[k]

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
    patterns = list(_DEFAULT_WATCHED_FILES) + list(config().cache_invalidation_files)
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
    cfg = config()
    old_commit = state().old_git_commit
    if cfg.use_git_change_detection and old_commit is not None:
        git_changed = git_changed_non_py_files(old_commit)
        if git_changed is not None:
            # also catch explicitly-registered files that git ignores
            changed = git_changed | _changed_hashed_files(restrict_to=cfg.cache_invalidation_files)
        else:
            changed = _changed_hashed_files()
    else:
        changed = _changed_hashed_files()
    return {p for p in changed if not _is_excluded(p, cfg)}


def _compute_baseline_file_hashes() -> dict[str, str]:
    """The set of non-.py files to track, hashed. Always includes the curated/user-glob
    files; when git is available it also records every tracked non-.py file (minus noise)
    so a later git-less run can still detect changes to them.
    """
    cfg = config()
    hashes = compute_watched_file_hashes()
    if cfg.use_git_change_detection:
        tracked = git_tracked_non_py_files()
        if tracked is not None:
            hashes.update(_hash_files(sorted(p for p in tracked if not _is_excluded(p, cfg))))
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

    policy = config().on_dependency_change
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
    new_fp = config().config_fingerprint()
    changed_groups = {g for g in new_fp if old_fp.get(g) != new_fp[g]} if old_fp else set()

    dependency_rerun = _report_watched_file_changes()

    # Global groups change how *every* test runs / which tests map to a function, so no
    # subset of results is safe to keep -> full reset and full stats recollection.
    if changed_groups & {"test_execution", "test_selection"} or dependency_rerun:
        _reset_mutant_results(lambda key, exit_code: True)
        state().duration_by_test.clear()
        state().tests_by_mangled_function_name.clear()
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
    runner: MutantRunner,
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
        if config().track_dependencies and invalidate_stale_callers:
            _invalidate_stale_dependency_edges()
        save_stats()

        # Run incremental stats
        with CatchOutput(spinner_title="Listing all tests") as output_catcher:
            set_mutant_under_test("list_all_tests")
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


def mutation_score_to_hex_color(score: float) -> str:
    clamped_score = max(0.0, min(100.0, score))
    hue = (clamped_score / 100.0) * (120.0 / 360.0)
    red, green, blue = hls_to_rgb(hue, 0.5, 1.0)
    return f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"


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


@cli.command()
@click.option(
    "--input",
    "input_path",
    default="mutants/mutmut-cicd-stats.json",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--output", required=True, type=click.Path(dir_okay=False, path_type=Path))
@click.option("--label", default="mutation", show_default=True)
def badge(input_path: Path, output: Path, label: str) -> None:
    try:
        with input_path.open() as f:
            stats = json.load(f)
    except JSONDecodeError as e:
        raise click.ClickException(f"{input_path} does not contain valid JSON") from e

    tested = int(stats.get("total", 0)) - int(stats.get("skipped", 0))
    score = 0.0 if tested <= 0 else ((int(stats.get("killed", 0)) + int(stats.get("timeout", 0))) / tested) * 100
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as f:
        json.dump(
            {
                "schemaVersion": 1,
                "label": label,
                "message": f"{score:.1f}%",
                "color": mutation_score_to_hex_color(score),
            },
            f,
            indent=4,
        )
        f.write("\n")
    print(f"Saved mutation badge to {output}")


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
    recorded = set(state().tests_by_mangled_function_name.keys())
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
    tests = state().tests_by_mangled_function_name.get(mangled_name_from_mutant_name(mutant_name), set())
    return sum(state().duration_by_test[t] for t in tests)


@cli.command()
@click.argument("mutant_names", required=False, nargs=-1)
def print_time_estimates(mutant_names: tuple[str, ...]) -> None:
    assert isinstance(mutant_names, (tuple, list)), mutant_names

    runner = get_mutant_runner()

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


def _register_mutant_result(
    result: MutantResult,
    mutation_data_by_mutant_name: dict[str, SourceFileMutationData],
) -> None:
    """Record a completed mutant's exit code and duration onto its mutation data."""
    mutation_data = mutation_data_by_mutant_name[result.mutant_name]
    # Writing a key the meta file does not already know about would silently create a
    # phantom mutant instead of recording a verdict, so fail loudly on a name mismatch.
    assert result.mutant_name in mutation_data.exit_code_by_key, (
        f"{result.mutant_name} is not a known mutant of {mutation_data.path}"
    )
    mutation_data.exit_code_by_key[result.mutant_name] = result.exit_code
    mutation_data.durations_by_key[result.mutant_name] = result.duration
    mutation_data.save()


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
    set_mutant_under_test("mutant_generation")

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
    if config().type_check_command:
        with CatchOutput(spinner_title="Filtering mutations with type checker"):
            mutants_caught_by_type_checker = filter_mutants_with_type_checker()

    # TODO: config/option for the test runner (e.g. HammettRunner)
    runner: MutantRunner = get_mutant_runner(max_children)

    # TODO: run these steps only if we have mutants to test

    collect_or_load_stats(
        runner,
        mutants_caught_by_type_checker=mutants_caught_by_type_checker,
        apply_config_invalidation=True,
    )

    mutants, source_file_mutation_data_by_path = collect_source_file_mutation_data(mutant_names=mutant_names)

    _check_test_to_mutant_associations(source_file_mutation_data_by_path)

    set_mutant_under_test("")
    with CatchOutput(spinner_title="Running clean tests") as output_catcher:
        tests = tests_for_mutant_names(mutant_names)

        clean_test_exit_code = runner.run_clean_tests(tests=tests)
        if clean_test_exit_code != 0:
            output_catcher.dump_output()
            print("Failed to run clean test")
            exit(1)
    print("    done")

    # this can't be the first thing, because it can fail deep inside pytest/django setup and then everything is destroyed
    run_forced_fail_test(runner)

    # Maps each submitted mutant to its mutation data, for result registration.
    mutation_data_by_mutant_name: dict[str, SourceFileMutationData] = {}
    count_tried = 0

    def drain_one_result() -> None:
        nonlocal count_tried
        result = runner.wait_for_result()
        if config().debug:
            print("    worker exit code", result.exit_code)
        _register_mutant_result(result, mutation_data_by_mutant_name)
        count_tried += 1

    # Run estimated fast mutants first, calculated as the estimated time for a surviving mutant.
    mutants = sorted(mutants, key=lambda x: estimated_worst_case_time(x[1]))
    start = datetime.now()
    runner.startup()
    try:
        print("Running mutation testing")

        # Now do mutation
        for mutation_data, mutant_name, result in mutants:
            mutant_name = mutant_name.replace("__init__.", "")
            tests = state().tests_by_mangled_function_name.get(mangled_name_from_mutant_name(mutant_name), set())
            estimated_time_of_tests = sum(state().duration_by_test[test_name] for test_name in tests)
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

            cfg = config()
            # signal SIGXCPU after this many CPU seconds; the runner adds one more before SIGKILL.
            cpu_time_limit_s = ceil((estimated_time_of_tests + cfg.timeout_constant) * cfg.timeout_multiplier * 2)

            # Block for a free worker slot before submitting more work.
            while not runner.has_capacity():
                drain_one_result()

            mutation_data_by_mutant_name[mutant_name] = mutation_data
            runner.submit(mutant_name, list(tests), cpu_time_limit_s, estimated_time_of_tests)

        runner.signal_work_complete()

        try:
            while runner.pending_count() > 0:
                drain_one_result()
        except ChildProcessError:
            pass
    except KeyboardInterrupt:
        print("Stopping...")
        runner.stop_all_workers()
    finally:
        runner.shutdown()

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
            for name, tests_of_this_name in state().tests_by_mangled_function_name.items():
                if fnmatch.fnmatch(name, mutant_name):
                    tests |= set(tests_of_this_name)
        else:
            tests |= set(state().tests_by_mangled_function_name[mangled_name_from_mutant_name(mutant_name)])
    return tests


@cli.command()
@click.option("--all", default=False)
def results(all: bool) -> None:
    for path in walk_mutatable_files():
        m = SourceFileMutationData(path=path)
        m.load()
        for k, v in m.exit_code_by_key.items():
            status = status_by_exit_code[v]
            if status == "killed" and not all:
                continue
            print(f"    {k}: {status}")


@cli.command()
@click.argument("mutant_name")
def show(mutant_name: str) -> None:
    m = find_mutant(mutant_name)
    print(f"# {mutant_name}: {status_by_exit_code[m.exit_code_by_key[mutant_name]]}")
    print(get_diff_for_mutant(mutant_name, path=m.path))
    return


@cli.command()
@click.argument("mutant_name")
def apply(mutant_name: str) -> None:
    # try:
    apply_mutant(mutant_name)
    # except FileNotFoundError as e:
    #     print(e)


@cli.command()
@click.option("--show-killed", is_flag=True, default=False, help="Display mutants killed by tests and type checker.")
def browse(show_killed: bool) -> None:
    run_result_browser(show_killed=show_killed)


if __name__ == "__main__":
    cli()
