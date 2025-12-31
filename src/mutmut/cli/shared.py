import itertools
import os
import sys
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from io import TextIOBase
from time import process_time
from typing import Protocol, cast

from mutmut.config import get_config
from mutmut.meta import SourceFileMutationData, load_stats, save_stats
from mutmut.mutation import (
    MutmutProgrammaticFailException,
    calculate_summary_stats,
    collected_test_names,
    utcnow,
)
from mutmut.runners import CollectTestsFailedException, TestRunner
from mutmut.state import MutmutState


class StatusPrinterType(Protocol):
    def __call__(self, message: str, *, force_output: bool = False) -> None: ...


spinner = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")


def status_printer() -> StatusPrinterType:
    """Manage the printing and in-place updating of a line of characters.

    .. note::
        If the string is longer than a line, then in-place updating may not
        work (it will print a new line at each refresh).
    """
    last_len = [0]
    last_update = [datetime(1900, 1, 1, tzinfo=UTC)]
    update_threshold = timedelta(seconds=0.1)

    def p(s: str, *, force_output: bool = False) -> None:
        if not force_output and (utcnow() - last_update[0]) < update_threshold:
            return
        s = next(spinner) + " " + s
        len_s = len(s)
        output = "\r" + s + (" " * max(last_len[0] - len_s, 0))
        stdout = sys.__stdout__ or sys.stdout
        if stdout is None:
            msg = "stdout is not available"
            raise RuntimeError(msg)
        stdout.write(output)
        stdout.flush()
        last_len[0] = len_s

    return cast("StatusPrinterType", p)


print_status: StatusPrinterType = status_printer()


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


def run_forced_fail_test(runner: TestRunner, state: MutmutState) -> None:
    os.environ["MUTANT_UNDER_TEST"] = "fail"
    with CatchOutput(state=state, spinner_title="Running forced fail test") as catcher:
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
        *,
        state: MutmutState,
        callback: Callable[[str], None] = lambda _s: None,
        spinner_title: str | None = None,
    ):
        self.strings = []
        self.spinner_title = spinner_title or ""
        config = state.config
        if config is not None and config.debug:
            self.spinner_title += "\n"
        self._state = state

        class StdOutRedirect(TextIOBase):
            def __init__(self, catcher: CatchOutput):
                self.catcher = catcher

            def write(self, s: str) -> int:
                callback(s)
                if spinner_title:
                    print_status(spinner_title)
                self.catcher.strings.append(s)
                return len(s)

        self.redirect = StdOutRedirect(self)

    # noinspection PyMethodMayBeStatic
    @staticmethod
    def stop():
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    def start(self):
        if self.spinner_title:
            print_status(self.spinner_title)
        sys.stdout = self.redirect
        sys.stderr = self.redirect
        config = self._state.config
        if config is not None and config.debug:
            self.stop()

    def dump_output(self):
        self.stop()
        print()
        for line in self.strings:
            print(line, end="")

    def __enter__(self):
        """Start redirecting stdout/stderr and return the catcher."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore the original stdout/stderr streams."""
        self.stop()
        if self.spinner_title:
            print()


def run_stats_collection(
    runner: TestRunner,
    state: MutmutState,
    tests: Iterable[str] | None = None,
) -> None:
    if tests is None:
        tests = []  # Meaning all...

    config = get_config(state)
    os.environ["MUTANT_UNDER_TEST"] = "stats"
    os.environ["PY_IGNORE_IMPORTMISMATCH"] = "1"
    start_cpu_time = process_time()

    with CatchOutput(state=state, spinner_title="Running stats") as output_catcher:
        collect_stats_exit_code = runner.run_stats(tests=tests)
        if collect_stats_exit_code != 0:
            output_catcher.dump_output()
            print(f"failed to collect stats. runner returned {collect_stats_exit_code}")
            sys.exit(1)
        # ensure that at least one mutant has associated tests
        num_associated_tests = sum(len(tests) for tests in state.tests_by_mangled_function_name.values())
        if num_associated_tests == 0:
            output_catcher.dump_output()
            print(
                "Stopping early, because we could not find any test case for any mutant. "
                "It seems that the selected tests do not cover any code that we mutated."
            )
            if not config.debug:
                print("You can set debug=true to see the executed test names in the output above.")
            else:
                print("In the last pytest run above, you can see which tests we executed.")
            print("You can use mutmut browse to check which parts of the source code we mutated.")
            print(
                "If some of the mutated code should be covered by the executed tests, "
                "consider opening an issue (with a MRE if possible)."
            )
            sys.exit(1)

    print("    done")
    if not tests:  # again, meaning all
        state.stats_time = process_time() - start_cpu_time

    if not collected_test_names(state):
        print("failed to collect stats, no active tests found")
        sys.exit(1)

    save_stats(state)


def collect_or_load_stats(runner: TestRunner, state: MutmutState) -> None:
    did_load = load_stats(state)

    if not did_load:
        # Run full stats
        run_stats_collection(runner, state)
    else:
        # Run incremental stats
        with CatchOutput(state=state, spinner_title="Listing all tests") as output_catcher:
            os.environ["MUTANT_UNDER_TEST"] = "list_all_tests"
            try:
                all_tests_result = runner.list_all_tests()
            except CollectTestsFailedException:
                output_catcher.dump_output()
                print("Failed to collect list of tests")
                sys.exit(1)

        all_tests_result.clear_out_obsolete_test_names()

        new_tests = all_tests_result.new_tests()

        if new_tests:
            print(f"Found {len(new_tests)} new tests, rerunning stats collection")
            run_stats_collection(runner, state, tests=new_tests)
