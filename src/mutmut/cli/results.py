import click

from mutmut.config import ensure_config_loaded
from mutmut.meta import SourceFileMutationData
from mutmut.mutation import status_by_exit_code, walk_source_files


@click.command()
@click.option("--all", "show_all", default=False)
def results(*, show_all: bool) -> None:
    ensure_config_loaded()
    for path in walk_source_files():
        if not str(path).endswith(".py"):
            continue
        m = SourceFileMutationData(path=path)
        m.load()
        for k, v in m.exit_code_by_key.items():
            status = status_by_exit_code[v]
            if status == "killed" and not show_all:
                continue
            print(f"    {k}: {status}")
