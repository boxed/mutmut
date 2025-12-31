import click

from mutmut.config import ensure_config_loaded
from mutmut.mutation import get_diff_for_mutant
from mutmut.state import MutmutState


@click.command()
@click.argument("mutant_name")
@click.pass_obj
def show(state: MutmutState, mutant_name: str) -> None:
    ensure_config_loaded(state)
    print(get_diff_for_mutant(state, mutant_name))
