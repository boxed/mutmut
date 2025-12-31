import click

from mutmut.config import ensure_config_loaded
from mutmut.mutation import apply_mutant


@click.command()
@click.argument("mutant_name")
def apply(mutant_name: str) -> None:
    # try:
    ensure_config_loaded()
    apply_mutant(mutant_name)
    # except FileNotFoundError as e:
    #     print(e)
