import sys

import click

from nootnoot.mutation import tests_for_mutant_names
from nootnoot.persistence import load_stats
from nootnoot.state import NootNootState


@click.command()
@click.argument("mutant_name", required=True, nargs=1)
@click.pass_obj
def tests_for_mutant(state: NootNootState, mutant_name: str) -> None:
    if not load_stats(state):
        print(
            "Failed to load stats. Please run nootnoot first to collect stats.",
            file=sys.stderr,
        )
        sys.exit(1)

    tests = tests_for_mutant_names(state, [mutant_name])
    for test in sorted(tests):
        print(test)
