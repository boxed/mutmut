from __future__ import annotations

import os
import sys
from io import TextIOBase
from time import process_time
from typing import IO, TYPE_CHECKING

from rich.console import Console

from nootnoot.config import get_config
from nootnoot.mutation import (
    NootNootProgrammaticFailException,
    calculate_summary_stats,
    collected_test_names,
)
from nootnoot.persistence import load_stats, save_stats
from nootnoot.runners import CollectTestsFailedException, TestRunner

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from rich.status import Status

    from nootnoot.meta import SourceFileMutationData
    from nootnoot.state import NootNootState

console = Console(
    file=sys.__stderr__ or sys.stderr,
)  # use rich (via textual) for deterministic spinner instead of reimplementing animation.


def print_status(message: str, *, force_output: bool = False) -> None:
    console.print(message)
    if force_output:
        console.file.flush()


def print_stats(
    source_file_mutation_data_by_path: dict[str, SourceFileMutationData],
    *,
    force_output: bool = False,
) -> None:
    s = calculate_summary_stats(source_file_mutation_data_by_path)
    summary = (
        f"{(s.total - s.not_checked)}/{s.total}  🎉 {s.killed} 🫥 {s.no_tests}  "
        f"⏰ {s.timeout}  🤔 {s.suspicious}  🙁 {s.survived}  🔇 {s.skipped}"
    )
    print_status(summary, force_output=force_output)


def run_forced_fail_test(runner: TestRunner, state: NootNootState) -> None:
    os.environ["MUTANT_UNDER_TEST"] = "fail"
    with CatchOutput(
        state=state,
        spinner_title="Running forced fail test",
        output_stream=sys.stderr,
    ) as catcher:
        try:
            if runner.run_forced_fail() == 0:
                catcher.dump_output()
                print("FAILED: Unable to force test failures", file=sys.stderr)
                raise SystemExit(1)
        except NootNootProgrammaticFailException:
            pass
    os.environ["MUTANT_UNDER_TEST"] = ""
    print("    done", file=sys.stderr)


class CatchOutput:
    def __init__(
        self,
        *,
        state: NootNootState,
        callback: Callable[[str], None] = lambda _s: None,
        spinner_title: str | None = None,
        output_stream: TextIOBase | IO[str] | None = None,
    ):
        self.strings = []
        self.spinner_title = spinner_title or ""
        config = state.config
        self._state = state
        self._status: Status | None = None
        self._is_debug = config is not None and config.debug
        self._output_stream = output_stream or sys.stderr

        class StdOutRedirect(TextIOBase):
            def __init__(self, catcher: CatchOutput):
                self.catcher = catcher

            def write(self, s: str) -> int:
                callback(s)
                self.catcher.strings.append(s)
                return len(s)

        self.redirect = StdOutRedirect(self)

    def stop(self):
        if self._status is not None:
            self._status.stop()
            self._status = None
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    def start(self):
        if self.spinner_title and not self._is_debug:
            self._status = console.status(self.spinner_title, spinner="dots")
            self._status.start()
        elif self.spinner_title:
            console.print(self.spinner_title)
            console.print()
        sys.stdout = self.redirect
        sys.stderr = self.redirect
        if self._is_debug:
            self.stop()

    def dump_output(self):
        self.stop()
        print(file=self._output_stream)
        for line in self.strings:
            print(line, end="", file=self._output_stream)

    def __enter__(self):
        """Start redirecting stdout/stderr and return the catcher."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore the original stdout/stderr streams."""
        self.stop()
        if self.spinner_title:
            print(file=self._output_stream)


def run_stats_collection(
    runner: TestRunner,
    state: NootNootState,
    tests: Iterable[str] | None = None,
) -> None:
    if tests is None:
        tests = []  # Meaning all...

    config = get_config(state)
    os.environ["MUTANT_UNDER_TEST"] = "stats"
    os.environ["PY_IGNORE_IMPORTMISMATCH"] = "1"
    start_cpu_time = process_time()

    with CatchOutput(
        state=state,
        spinner_title="Running stats",
        output_stream=sys.stderr,
    ) as output_catcher:
        collect_stats_exit_code = runner.run_stats(tests=tests)
        if collect_stats_exit_code != 0:
            output_catcher.dump_output()
            print(
                f"failed to collect stats. runner returned {collect_stats_exit_code}",
                file=sys.stderr,
            )
            sys.exit(1)
        # ensure that at least one mutant has associated tests
        num_associated_tests = sum(len(tests) for tests in state.tests_by_mangled_function_name.values())
        if num_associated_tests == 0:
            output_catcher.dump_output()
            print(
                "Stopping early, because we could not find any test case for any mutant. "
                "It seems that the selected tests do not cover any code that we mutated.",
                file=sys.stderr,
            )
            if not config.debug:
                print(
                    "You can set debug=true to see the executed test names in the output above.",
                    file=sys.stderr,
                )
            else:
                print(
                    "In the last pytest run above, you can see which tests we executed.",
                    file=sys.stderr,
                )
            print(
                "You can use nootnoot browse to check which parts of the source code we mutated.",
                file=sys.stderr,
            )
            print(
                "If some of the mutated code should be covered by the executed tests, "
                "consider opening an issue (with a MRE if possible).",
                file=sys.stderr,
            )
            sys.exit(1)

    print("    done", file=sys.stderr)
    if not tests:  # again, meaning all
        state.stats_time = process_time() - start_cpu_time

    if not collected_test_names(state):
        print("failed to collect stats, no active tests found", file=sys.stderr)
        sys.exit(1)

    save_stats(state)


def collect_or_load_stats(runner: TestRunner, state: NootNootState) -> None:
    did_load = load_stats(state)

    if not did_load:
        # Run full stats
        run_stats_collection(runner, state)
    else:
        # Run incremental stats
        with CatchOutput(
            state=state,
            spinner_title="Listing all tests",
            output_stream=sys.stderr,
        ) as output_catcher:
            os.environ["MUTANT_UNDER_TEST"] = "list_all_tests"
            try:
                all_tests_result = runner.list_all_tests()
            except CollectTestsFailedException:
                output_catcher.dump_output()
                print("Failed to collect list of tests", file=sys.stderr)
                sys.exit(1)

        all_tests_result.clear_out_obsolete_test_names()

        new_tests = all_tests_result.new_tests()

        if new_tests:
            print(
                f"Found {len(new_tests)} new tests, rerunning stats collection",
                file=sys.stderr,
            )
            run_stats_collection(runner, state, tests=new_tests)
