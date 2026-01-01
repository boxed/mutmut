import click

from nootnoot.app.config import ensure_config_loaded
from nootnoot.app.mutation import apply_mutant
from nootnoot.app.state import NootNootState


@click.command()
@click.argument("mutant_name")
@click.pass_obj
def apply(state: NootNootState, mutant_name: str) -> None:
    # try:
    ensure_config_loaded(state)
    apply_mutant(state, mutant_name)
    # except FileNotFoundError as e:
    #     print(e)
