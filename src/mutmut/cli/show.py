import click

from mutmut.config import ensure_config_loaded
from mutmut.mutation import get_diff_for_mutant


@click.command()
@click.argument("mutant_name")
def show(mutant_name: str) -> None:
    ensure_config_loaded()
    print(get_diff_for_mutant(mutant_name))
