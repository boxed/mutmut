import click

from nootnoot.config import ensure_config_loaded
from nootnoot.meta import SourceFileMutationData
from nootnoot.mutation import status_by_exit_code, walk_source_files
from nootnoot.state import NootNootState


@click.command()
@click.option("--all", "show_all", default=False)
@click.pass_obj
def results(state: NootNootState, *, show_all: bool) -> None:
    ensure_config_loaded(state)
    for path in walk_source_files(state):
        if not str(path).endswith(".py"):
            continue
        m = SourceFileMutationData(path=path)
        m.load()
        for k, v in m.exit_code_by_key.items():
            status = status_by_exit_code[v]
            if status == "killed" and not show_all:
                continue
            print(f"    {k}: {status}")
