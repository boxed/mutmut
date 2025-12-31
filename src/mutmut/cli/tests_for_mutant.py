import sys

import click

from mutmut.meta import load_stats
from mutmut.mutation import tests_for_mutant_names


@click.command()
@click.argument("mutant_name", required=True, nargs=1)
def tests_for_mutant(mutant_name: str) -> None:
    if not load_stats():
        print("Failed to load stats. Please run mutmut first to collect stats.")
        sys.exit(1)

    tests = tests_for_mutant_names([mutant_name])
    for test in sorted(tests):
        print(test)
