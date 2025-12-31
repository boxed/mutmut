import click

from mutmut.config import ensure_config_loaded
from mutmut.mutation import collect_source_file_mutation_data, estimated_worst_case_time
from mutmut.runners import PytestRunner
from mutmut.state import MutmutState

from .shared import collect_or_load_stats


@click.command()
@click.argument("mutant_names", required=False, nargs=-1)
@click.pass_obj
def print_time_estimates(state: MutmutState, mutant_names: tuple[str, ...] | list[str]) -> None:
    if not isinstance(mutant_names, (tuple, list)):
        msg = f"mutant_names must be tuple or list, got {type(mutant_names)}"
        raise TypeError(msg)
    ensure_config_loaded(state)

    runner = PytestRunner(state)
    runner.prepare_main_test_run()

    collect_or_load_stats(runner, state)

    mutants, _source_file_mutation_data_by_path = collect_source_file_mutation_data(
        mutant_names=mutant_names,
        state=state,
    )

    times_and_keys = [
        (estimated_worst_case_time(state, mutant_name), mutant_name) for m, mutant_name, result in mutants
    ]

    for time, key in sorted(times_and_keys):
        if not time:
            print("<no tests>", key)
        else:
            print(f"{int(time * 1000)}ms", key)
