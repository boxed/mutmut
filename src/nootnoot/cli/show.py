import click

from nootnoot.app.config import ensure_config_loaded
from nootnoot.app.mutation import get_diff_for_mutant
from nootnoot.app.state import NootNootState


@click.command()
@click.argument("mutant_name")
@click.pass_obj
def show(state: NootNootState, mutant_name: str) -> None:
    ensure_config_loaded(state)
    print(get_diff_for_mutant(state, mutant_name))
