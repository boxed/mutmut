import click

from mutmut.config import ensure_config_loaded
from mutmut.mutation import apply_mutant
from mutmut.state import MutmutState


@click.command()
@click.argument("mutant_name")
@click.pass_obj
def apply(state: MutmutState, mutant_name: str) -> None:
    # try:
    ensure_config_loaded(state)
    apply_mutant(state, mutant_name)
    # except FileNotFoundError as e:
    #     print(e)
