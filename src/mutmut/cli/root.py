import click

from .apply import apply
from .browse import browse
from .print_time_estimates import print_time_estimates
from .results import results
from .run import run
from .show import show
from .tests_for_mutant import tests_for_mutant


@click.group()
@click.version_option()
def cli() -> None:
    pass


cli.add_command(print_time_estimates)
cli.add_command(tests_for_mutant)
cli.add_command(run)
cli.add_command(results)
cli.add_command(show)
cli.add_command(apply)
cli.add_command(browse)
