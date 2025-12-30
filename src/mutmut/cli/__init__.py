import gc
import itertools
import os
import resource
import signal
import subprocess  # noqa: S404
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from io import TextIOBase
from math import ceil
from multiprocessing import set_start_method
from pathlib import Path
from threading import Thread
from time import process_time, sleep
from typing import Any, ClassVar, Protocol, cast

import click
from rich.text import Text
from setproctitle import setproctitle

import mutmut
from mutmut.config import ensure_config_loaded, get_config
from mutmut.meta import (
    START_TIMES_BY_PID_LOCK,
    SourceFileMutationData,
    load_stats,
    save_stats,
)
from mutmut.mutation import (
    MutmutProgrammaticFailException,
    Stat,
    apply_mutant,
    calculate_summary_stats,
    collect_source_file_mutation_data,
    collect_stat,
    collected_test_names,
    copy_also_copy_files,
    copy_src_dir,
    create_mutants,
    emoji_by_status,
    estimated_worst_case_time,
    get_diff_for_mutant,
    mangled_name_from_mutant_name,
    setup_source_paths,
    status_by_exit_code,
    store_lines_covered_by_tests,
    tests_for_mutant_names,
    unused,
    utcnow,
    walk_source_files,
)
from mutmut.runners import CollectTestsFailedException, PytestRunner


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


def run_forced_fail_test(runner):
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
    def __init__(self, callback=lambda _s: None, spinner_title=None):
        self.strings = []
        self.spinner_title = spinner_title or ""
        config = mutmut.config
        if config is not None and config.debug:
            self.spinner_title += "\n"

        class StdOutRedirect(TextIOBase):
            def __init__(self, catcher):
                self.catcher = catcher

            def write(self, s):
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
        config = mutmut.config
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


@click.group()
@click.version_option()
def cli():
    pass


def run_stats_collection(runner, tests=None):
    if tests is None:
        tests = []  # Meaning all...

    config = get_config()
    os.environ["MUTANT_UNDER_TEST"] = "stats"
    os.environ["PY_IGNORE_IMPORTMISMATCH"] = "1"
    start_cpu_time = process_time()

    with CatchOutput(spinner_title="Running stats") as output_catcher:
        collect_stats_exit_code = runner.run_stats(tests=tests)
        if collect_stats_exit_code != 0:
            output_catcher.dump_output()
            print(f"failed to collect stats. runner returned {collect_stats_exit_code}")
            sys.exit(1)
        # ensure that at least one mutant has associated tests
        num_associated_tests = sum(len(tests) for tests in mutmut.tests_by_mangled_function_name.values())
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
        mutmut.stats_time = process_time() - start_cpu_time

    if not collected_test_names():
        print("failed to collect stats, no active tests found")
        sys.exit(1)

    save_stats()


def collect_or_load_stats(runner):
    did_load = load_stats()

    if not did_load:
        # Run full stats
        run_stats_collection(runner)
    else:
        # Run incremental stats
        with CatchOutput(spinner_title="Listing all tests") as output_catcher:
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
            run_stats_collection(runner, tests=new_tests)


@cli.command()
@click.argument("mutant_names", required=False, nargs=-1)
def print_time_estimates(mutant_names: tuple[str, ...] | list[str]) -> None:
    if not isinstance(mutant_names, (tuple, list)):
        msg = f"mutant_names must be tuple or list, got {type(mutant_names)}"
        raise TypeError(msg)
    ensure_config_loaded()

    runner = PytestRunner()
    runner.prepare_main_test_run()

    collect_or_load_stats(runner)

    mutants, _source_file_mutation_data_by_path = collect_source_file_mutation_data(mutant_names=mutant_names)

    times_and_keys = [
        (estimated_worst_case_time(mutant_name), mutant_name) for m, mutant_name, result in mutants
    ]

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
        sys.exit(1)

    tests = tests_for_mutant_names([mutant_name])
    for test in sorted(tests):
        print(test)


def stop_all_children(mutants):
    for m, _, _ in mutants:
        m.stop_children()


# used to copy the global mutmut.config to subprocesses
with suppress(RuntimeError):
    set_start_method("fork")


def timeout_checker(mutants):
    def inner_timeout_checker():
        while True:
            sleep(1)

            now = utcnow()
            for m, mutant_name, _result in mutants:
                # copy dict inside lock, so it is not modified by another process while we iterate it
                with START_TIMES_BY_PID_LOCK:
                    start_times_by_pid = dict(m.start_time_by_pid)
                for pid, start_time in start_times_by_pid.items():
                    run_time = now - start_time
                    if run_time.total_seconds() > (m.estimated_time_of_tests_by_mutant[mutant_name] + 1) * 15:
                        with suppress(ProcessLookupError):
                            os.kill(pid, signal.SIGXCPU)

    return inner_timeout_checker


@cli.command()
@click.option("--max-children", type=int)
@click.argument("mutant_names", required=False, nargs=-1)
def run(mutant_names: tuple[str, ...] | list[str], *, max_children: int | None) -> None:
    if not isinstance(mutant_names, (tuple, list)):
        msg = f"mutant_names must be tuple or list, got {type(mutant_names)}"
        raise TypeError(msg)
    _run(mutant_names, max_children)


# separate function, so we can call it directly from the tests
def _run(  # noqa: PLR0912, PLR0914, PLR0915
    mutant_names: tuple[str, ...] | list[str],
    max_children: int | None,
) -> None:
    # TODO: run no-ops once in a while to detect if we get false negatives
    # TODO: we should be able to get information on which tests killed mutants,
    # which means we can get a list of tests and how many mutants each test kills.
    # Those that kill zero mutants are redundant!
    os.environ["MUTANT_UNDER_TEST"] = "mutant_generation"
    ensure_config_loaded()
    config = get_config()

    if max_children is None:
        max_children = os.cpu_count() or 4

    start = utcnow()
    Path("mutants").mkdir(exist_ok=True, parents=True)
    with CatchOutput(spinner_title="Generating mutants"):
        copy_src_dir()
        copy_also_copy_files()
        setup_source_paths()
        store_lines_covered_by_tests()
        create_mutants(max_children)

    time = utcnow() - start
    print(f"    done in {round(time.total_seconds() * 1000)}ms")

    # TODO: config/option for runner
    # runner = HammettRunner()
    runner = PytestRunner()
    runner.prepare_main_test_run()

    # TODO: run these steps only if we have mutants to test

    collect_or_load_stats(runner)

    mutants, source_file_mutation_data_by_path = collect_source_file_mutation_data(mutant_names=mutant_names)

    os.environ["MUTANT_UNDER_TEST"] = ""
    with CatchOutput(spinner_title="Running clean tests") as output_catcher:
        tests = tests_for_mutant_names(mutant_names)

        clean_test_exit_code = runner.run_tests(mutant_name=None, tests=tests)
        if clean_test_exit_code != 0:
            output_catcher.dump_output()
            print("Failed to run clean test")
            sys.exit(1)
    print("    done")

    # this can't be the first thing, because it can fail deep inside pytest/django
    # setup and then everything is destroyed
    run_forced_fail_test(runner)

    runner.prepare_main_test_run()

    def read_one_child_exit_status():
        pid, wait_status = os.wait()
        exit_code = os.waitstatus_to_exitcode(wait_status)
        if config.debug:
            print("    worker exit code", exit_code)
        source_file_mutation_data_by_pid[pid].register_result(pid=pid, exit_code=exit_code)

    source_file_mutation_data_by_pid: dict[
        int, SourceFileMutationData
    ] = {}  # many pids map to one MutationData
    running_children = 0
    count_tried = 0

    # Run estimated fast mutants first, calculated as the estimated time for a surviving mutant.
    mutants = sorted(mutants, key=lambda x: estimated_worst_case_time(x[1]))

    gc.freeze()

    start = utcnow()
    try:
        print("Running mutation testing")

        # Calculate times of tests
        for source_data, mutant_name, _ in mutants:
            normalized_mutant_name = mutant_name.replace("__init__.", "")
            tests = mutmut.tests_by_mangled_function_name.get(
                mangled_name_from_mutant_name(normalized_mutant_name), []
            )
            estimated_time_of_tests = sum(mutmut.duration_by_test[test_name] for test_name in tests)
            source_data.estimated_time_of_tests_by_mutant[normalized_mutant_name] = estimated_time_of_tests

        Thread(target=timeout_checker(mutants), daemon=True).start()

        # Now do mutation
        for source_data, mutant_name, previous_result in mutants:
            print_stats(source_file_mutation_data_by_path)

            normalized_mutant_name = mutant_name.replace("__init__.", "")

            # Rerun mutant if it's explicitly mentioned, but otherwise let the result stand
            if not mutant_names and previous_result is not None:
                continue

            tests = mutmut.tests_by_mangled_function_name.get(
                mangled_name_from_mutant_name(normalized_mutant_name), []
            )

            # print(tests)
            if not tests:
                source_data.exit_code_by_key[normalized_mutant_name] = 33
                source_data.save()
                continue

            pid = os.fork()
            if not pid:
                # In the child
                os.environ["MUTANT_UNDER_TEST"] = normalized_mutant_name
                setproctitle(f"mutmut: {normalized_mutant_name}")

                # Run fast tests first
                tests = sorted(tests, key=lambda test_name: mutmut.duration_by_test[test_name])
                if not tests:
                    os._exit(33)

                estimated_time_of_tests = source_data.estimated_time_of_tests_by_mutant[
                    normalized_mutant_name
                ]
                cpu_time_limit = ceil((estimated_time_of_tests + 1) * 30 + process_time())
                # signal SIGXCPU after <cpu_time_limit>. One second later signal
                # SIGKILL if it is still running
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_time_limit, cpu_time_limit + 1))

                with CatchOutput():
                    test_result = runner.run_tests(mutant_name=normalized_mutant_name, tests=tests)

                if test_result != 0:
                    # TODO: write failure information to stdout?
                    pass
                os._exit(test_result)
            else:
                # in the parent
                source_file_mutation_data_by_pid[pid] = source_data
                source_data.register_pid(pid=pid, key=normalized_mutant_name)
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

    t = utcnow() - start

    print_stats(source_file_mutation_data_by_path, force_output=True)
    print()
    print(f"{count_tried / t.total_seconds():.2f} mutations/second")

    if mutant_names:
        print()
        print("Mutant results")
        print("--------------")
        exit_code_by_key = {}
        # If the user gave a specific list of mutants, print result for these specifically
        for source_data, mutant_name, _ in mutants:
            normalized_mutant_name = mutant_name.replace("__init__.", "")
            exit_code_by_key[normalized_mutant_name] = source_data.exit_code_by_key[normalized_mutant_name]

        for mutant_name, exit_code in sorted(exit_code_by_key.items()):
            print(emoji_by_status.get(status_by_exit_code[exit_code], "?"), mutant_name)

        print()


@cli.command()
@click.option("--all", "show_all", default=False)
def results(*, show_all: bool) -> None:
    ensure_config_loaded()
    for path in walk_source_files():
        if not str(path).endswith(".py"):
            continue
        m = SourceFileMutationData(path=path)
        m.load()
        for k, v in m.exit_code_by_key.items():
            status = status_by_exit_code[v]
            if status == "killed" and not show_all:
                continue
            print(f"    {k}: {status}")


@cli.command()
@click.argument("mutant_name")
def show(mutant_name):
    ensure_config_loaded()
    print(get_diff_for_mutant(mutant_name))


@cli.command()
@click.argument("mutant_name")
def apply(mutant_name):
    # try:
    ensure_config_loaded()
    apply_mutant(mutant_name)
    # except FileNotFoundError as e:
    #     print(e)


@cli.command()
@click.option("--show-killed", is_flag=True, default=False, help="Display killed mutants.")
def browse(*, show_killed: bool) -> None:
    ensure_config_loaded()

    from rich.syntax import Syntax  # noqa: PLC0415
    from textual.app import App  # noqa: PLC0415
    from textual.containers import Container  # noqa: PLC0415
    from textual.widget import Widget  # noqa: PLC0415
    from textual.widgets import DataTable, Footer, Static  # noqa: PLC0415

    class ResultBrowser(App):
        CSS_PATH: ClassVar[str] = "result_browser_layout.tcss"
        BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
            ("q", "quit()", "Quit"),
            ("r", "retest_mutant()", "Retest mutant"),
            ("f", "retest_function()", "Retest function"),
            ("m", "retest_module()", "Retest module"),
            ("a", "apply_mutant()", "Apply mutant to disk"),
            ("t", "view_tests()", "View tests for mutant"),
        ]

        columns: ClassVar[list[tuple[str, Text | str]]] = [
            ("path", "Path"),
        ] + [(status, Text(emoji, justify="right")) for status, emoji in emoji_by_status.items()]

        cursor_type: ClassVar[str] = "row"

        def __init__(self, **kwargs: Any):
            super().__init__(**kwargs)
            self.loading_id: str | None = None
            self.source_file_mutation_data_and_stat_by_path: dict[
                str, tuple[SourceFileMutationData, Stat]
            ] = {}
            self.path_by_name: dict[str, Path] = {}

        def compose(self):
            unused(self)
            with Container(classes="container"):
                yield DataTable(id="files")
                yield DataTable(id="mutants")
            with Widget(id="diff_view_widget"):
                yield Static(id="description")
                yield Static(id="diff_view")
            yield Footer()

        def on_mount(self):
            # files table
            files_table = cast("DataTable", self.query_one("#files"))
            files_table.cursor_type = "row"
            for key, label in self.columns:
                files_table.add_column(key=key, label=label)

            # mutants table
            mutants_table = cast("DataTable", self.query_one("#mutants"))
            mutants_table.cursor_type = "row"
            mutants_table.add_columns("name", "status")

            self.read_data()
            self.populate_files_table()

        def read_data(self):
            config = get_config()
            self.source_file_mutation_data_and_stat_by_path = {}
            self.path_by_name = {}

            for p in walk_source_files():
                if config.should_ignore_for_mutation(p):
                    continue
                source_file_mutation_data = SourceFileMutationData(path=p)
                source_file_mutation_data.load()
                stat = collect_stat(source_file_mutation_data)

                self.source_file_mutation_data_and_stat_by_path[str(p)] = source_file_mutation_data, stat
                for name in source_file_mutation_data.exit_code_by_key:
                    self.path_by_name[name] = p

        def populate_files_table(self):
            files_table = cast("DataTable", self.query_one("#files"))
            # TODO: restore selection
            selected_row = files_table.cursor_row
            files_table.clear()

            for p, (_source_file_mutation_data, stat_for_row) in sorted(
                self.source_file_mutation_data_and_stat_by_path.items()
            ):
                row = [p] + [
                    Text(str(getattr(stat_for_row, k.replace(" ", "_"))), justify="right")
                    for k, _ in self.columns[1:]
                ]
                files_table.add_row(*row, key=str(p))

            files_table.move_cursor(row=selected_row)

        def on_data_table_row_highlighted(self, event):  # noqa: PLR0912, PLR0915
            if not event.row_key or not event.row_key.value:
                return
            if event.data_table.id == "files":
                mutants_table = cast("DataTable", self.query_one("#mutants"))
                mutants_table.clear()
                source_file_mutation_data, _stat = self.source_file_mutation_data_and_stat_by_path[
                    event.row_key.value
                ]
                for k, v in source_file_mutation_data.exit_code_by_key.items():
                    status = status_by_exit_code[v]
                    if status != "killed" or show_killed:
                        mutants_table.add_row(k, emoji_by_status[status], key=k)
            else:
                if event.data_table.id != "mutants":
                    msg = f"Unexpected data table {event.data_table.id}"
                    raise ValueError(msg)
                description_view = cast("Static", self.query_one("#description"))
                mutant_name = event.row_key.value
                self.loading_id = mutant_name
                path = self.path_by_name.get(mutant_name)
                if path is None:
                    msg = f"Path for mutant {mutant_name} is unknown"
                    raise ValueError(msg)
                source_file_mutation_data, _stat = self.source_file_mutation_data_and_stat_by_path[str(path)]

                exit_code = source_file_mutation_data.exit_code_by_key[mutant_name]
                status = status_by_exit_code[exit_code]
                estimated_duration = source_file_mutation_data.estimated_time_of_tests_by_mutant.get(
                    mutant_name, "?"
                )
                duration = source_file_mutation_data.durations_by_key.get(mutant_name, "?")

                view_tests_description = "(press t to view tests executed for this mutant)"

                match status:
                    case "killed":
                        description = f"Killed ({exit_code=}): Mutant caused a test to fail 🎉"
                    case "survived":
                        description = (
                            f"Survived ({exit_code=}): No test detected this mutant. {view_tests_description}"
                        )
                    case "skipped":
                        description = f"Skipped ({exit_code=})"
                    case "check was interrupted by user":
                        description = f"User interrupted ({exit_code=})"
                    case "timeout":
                        description = (
                            f"Timeout ({exit_code=}): Timed out because tests did not finish "
                            f"within {duration:.3f} seconds. Tests without mutation took "
                            f"{estimated_duration:.3f} seconds. {view_tests_description}"
                        )
                    case "no tests":
                        description = (
                            f"Untested ({exit_code=}): Skipped because selected tests do not "
                            "execute this code."
                        )
                    case "segfault":
                        description = f"Segfault ({exit_code=}): Running pytest with this mutant segfaulted."
                    case "suspicious":
                        description = (
                            f"Unknown ({exit_code=}): Running pytest with this mutant resulted "
                            "in an unknown exit code."
                        )
                    case "not checked":
                        description = "Not checked in the last mutmut run."
                    case _:
                        description = f"Unknown status ({exit_code=}, {status=})"
                description_view.update(f"\n {description}\n")

                diff_view = cast("Static", self.query_one("#diff_view"))
                diff_view.update("<loading code diff...>")

                def load_thread():
                    ensure_config_loaded()
                    try:
                        d = get_diff_for_mutant(event.row_key.value, path=path)
                        if event.row_key.value == self.loading_id:
                            diff_view.update(Syntax(d, "diff"))
                    except Exception as e:  # noqa: BLE001
                        diff_view.update(f"<{type(e)} {e}>")

                t = Thread(target=load_thread)
                t.start()

        def retest(self, pattern):
            self._run_subprocess_command("run", [pattern])

        def view_tests(self, mutant_name: str) -> None:
            self._run_subprocess_command("tests-for-mutant", [mutant_name])

        def _run_subprocess_command(self, command: str, args: list[str]) -> None:
            with self.suspend():
                browse_index = sys.argv.index("browse")
                initial_args = sys.argv[:browse_index]
                subprocess_args = [sys.executable, *initial_args, command, *args]
                print(">", *subprocess_args)
                subprocess.run(subprocess_args, check=False)  # noqa: S603
                input("press enter to return to browser")

            self.read_data()
            self.populate_files_table()

        def get_mutant_name_from_selection(self):
            mutants_table = cast("DataTable", self.query_one("#mutants"))
            if mutants_table.cursor_row is None:
                return None

            row = mutants_table.get_row_at(mutants_table.cursor_row)
            return str(row[0])

        def action_retest_mutant(self):
            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name is None:
                return
            self.retest(mutant_name)

        def action_retest_function(self):
            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name is None:
                return
            self.retest(mutant_name.rpartition("__mutmut_")[0] + "__mutmut_*")

        def action_retest_module(self):
            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name is None:
                return
            self.retest(mutant_name.rpartition(".")[0] + ".*")

        def action_apply_mutant(self):
            ensure_config_loaded()
            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name is None:
                return
            apply_mutant(mutant_name)

        def action_view_tests(self):
            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name is None:
                return
            self.view_tests(mutant_name)

    ResultBrowser().run()


if __name__ == "__main__":
    cli()
