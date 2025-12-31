import sys

import click

from mutmut.meta import load_stats
from mutmut.mutation import tests_for_mutant_names
from mutmut.state import MutmutState


@click.command()
@click.argument("mutant_name", required=True, nargs=1)
@click.pass_obj
def tests_for_mutant(state: MutmutState, mutant_name: str) -> None:
    if not load_stats(state):
        print("Failed to load stats. Please run mutmut first to collect stats.")
        sys.exit(1)

    tests = tests_for_mutant_names(state, [mutant_name])
    for test in sorted(tests):
        print(test)
