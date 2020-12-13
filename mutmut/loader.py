import sys

from importlib.abc import SourceLoader
from importlib.machinery import FileFinder
from pathlib import Path
from typing import Union

from . import Context
from . import mutate
from .cache import filename_and_mutation_id_from_pk
from .cache import update_line_numbers


def install(mutant_id: int):
    filename, mutation_id = filename_and_mutation_id_from_pk(mutant_id)
    update_line_numbers(filename)
    context = Context(
        mutation_id=mutation_id,
        filename=filename,
    )
    mutated, _ = mutate(context)
    mutant_file = Path(filename)

    class MutateLoader(SourceLoader):
        def __init__(self, fullname, path):
            self.fullname = fullname
            self.path = path

        def get_filename(self, fullname: str):
            return self.path

        def mutate(self, file: Path) -> str:
            if file.samefile(mutant_file):
                return mutated
            with open(file) as fp:
                return fp.read()

        def get_data(self, filename: Union[bytes, str]) -> bytes:
            """exec_module is already defined for us, we just have to provide a way
            of getting the source code of the module"""
            return self.mutate(Path(filename if isinstance(filename, str) else filename.decode())).encode()

    # insert the path hook ahead of other path hooks
    sys.path_hooks.insert(0, FileFinder.path_hook((MutateLoader, [".py"])))  # type: ignore
