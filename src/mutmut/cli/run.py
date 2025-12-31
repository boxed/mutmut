import gc
import os
import resource
import signal
import sys
from contextlib import suppress
from math import ceil
from multiprocessing import set_start_method
from pathlib import Path
from threading import Thread
from time import process_time, sleep

import click
from setproctitle import setproctitle

from mutmut.config import ensure_config_loaded, get_config
from mutmut.meta import START_TIMES_BY_PID_LOCK, SourceFileMutationData
from mutmut.mutation import (
    collect_source_file_mutation_data,
    copy_also_copy_files,
    copy_src_dir,
    create_mutants,
    emoji_by_status,
    estimated_worst_case_time,
    mangled_name_from_mutant_name,
    setup_source_paths,
    status_by_exit_code,
    store_lines_covered_by_tests,
    tests_for_mutant_names,
    utcnow,
)
from mutmut.runners import PytestRunner
from mutmut.state import MutmutState, set_state

from .shared import CatchOutput, collect_or_load_stats, print_stats, run_forced_fail_test


def stop_all_children(mutants):
    for m, _, _ in mutants:
        m.stop_children()


# used to copy the configuration when spawning subprocesses
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


@click.command()
@click.option("--max-children", type=int)
@click.argument("mutant_names", required=False, nargs=-1)
@click.pass_obj
def run(
    state: MutmutState,
    mutant_names: tuple[str, ...] | list[str],
    *,
    max_children: int | None,
) -> None:
    if not isinstance(mutant_names, (tuple, list)):
        msg = f"mutant_names must be tuple or list, got {type(mutant_names)}"
        raise TypeError(msg)
    _run(state, mutant_names, max_children)


# separate function, so we can call it directly from the tests
def _run(  # noqa: PLR0912, PLR0914, PLR0915
    state: MutmutState,
    mutant_names: tuple[str, ...] | list[str],
    max_children: int | None,
) -> None:
    # TODO: run no-ops once in a while to detect if we get false negatives
    # TODO: we should be able to get information on which tests killed mutants,
    # which means we can get a list of tests and how many mutants each test kills.
    # Those that kill zero mutants are redundant!
    set_state(state)
    os.environ["MUTANT_UNDER_TEST"] = "mutant_generation"
    if not hasattr(os, "fork"):
        print("mutmut run requires os.fork, which is unavailable on this platform.", file=sys.stderr)
        sys.exit(2)
    ensure_config_loaded(state)
    config = get_config(state)

    if max_children is None:
        max_children = os.cpu_count() or 4

    start = utcnow()
    Path("mutants").mkdir(exist_ok=True, parents=True)
    with CatchOutput(state=state, spinner_title="Generating mutants"):
        copy_src_dir(state)
        copy_also_copy_files(state)
        setup_source_paths()
        store_lines_covered_by_tests(state)
        create_mutants(max_children, state)

    time = utcnow() - start
    print(f"    done in {round(time.total_seconds() * 1000)}ms")

    # TODO: config/option for runner
    # runner = HammettRunner()
    runner = PytestRunner(state)
    runner.prepare_main_test_run()

    # TODO: run these steps only if we have mutants to test

    collect_or_load_stats(runner, state)

    mutants, source_file_mutation_data_by_path = collect_source_file_mutation_data(
        mutant_names=mutant_names,
        state=state,
    )

    os.environ["MUTANT_UNDER_TEST"] = ""
    with CatchOutput(state=state, spinner_title="Running clean tests") as output_catcher:
        tests = tests_for_mutant_names(state, mutant_names)

        clean_test_exit_code = runner.run_tests(mutant_name=None, tests=tests)
        if clean_test_exit_code != 0:
            output_catcher.dump_output()
            print("Failed to run clean test")
            sys.exit(1)
    print("    done")

    # this can't be the first thing, because it can fail deep inside pytest/django
    # setup and then everything is destroyed
    run_forced_fail_test(runner, state)

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
    mutants = sorted(mutants, key=lambda x: estimated_worst_case_time(state, x[1]))

    gc.freeze()

    start = utcnow()
    try:
        print("Running mutation testing")

        # Calculate times of tests
        for source_data, mutant_name, _ in mutants:
            normalized_mutant_name = mutant_name.replace("__init__.", "")
            tests = state.tests_by_mangled_function_name.get(
                mangled_name_from_mutant_name(normalized_mutant_name), []
            )
            estimated_time_of_tests = sum(state.duration_by_test[test_name] for test_name in tests)
            source_data.estimated_time_of_tests_by_mutant[normalized_mutant_name] = estimated_time_of_tests

        Thread(target=timeout_checker(mutants), daemon=True).start()

        # Now do mutation
        for source_data, mutant_name, previous_result in mutants:
            print_stats(source_file_mutation_data_by_path)

            normalized_mutant_name = mutant_name.replace("__init__.", "")

            # Rerun mutant if it's explicitly mentioned, but otherwise let the result stand
            if not mutant_names and previous_result is not None:
                continue

            tests = state.tests_by_mangled_function_name.get(
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
                tests = sorted(tests, key=lambda test_name: state.duration_by_test[test_name])
                if not tests:
                    os._exit(33)

                estimated_time_of_tests = source_data.estimated_time_of_tests_by_mutant[
                    normalized_mutant_name
                ]
                cpu_time_limit = ceil((estimated_time_of_tests + 1) * 30 + process_time())
                # signal SIGXCPU after <cpu_time_limit>. One second later signal
                # SIGKILL if it is still running
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_time_limit, cpu_time_limit + 1))

                with CatchOutput(state=state):
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
