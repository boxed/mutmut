import os
from collections.abc import Iterator
from contextlib import contextmanager
from os import walk
from os.path import isdir
from os.path import isfile
from pathlib import Path

from mutmut.configuration import Config


@contextmanager
def change_cwd(path: Path | str) -> Iterator[None]:
    old_cwd = Path(os.getcwd()).resolve()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def walk_all_files() -> Iterator[tuple[str, str]]:
    for path in Config.get().source_paths:
        if not isdir(path):
            if isfile(path):
                yield "", str(path)
                continue
        for root, dirs, files in walk(path):
            for filename in files:
                yield root, filename


def walk_source_files() -> Iterator[Path]:
    for root, filename in walk_all_files():
        if filename.endswith(".py"):
            yield Path(root) / filename


def walk_mutatable_files() -> Iterator[Path]:
    for path in walk_source_files():
        if Config.get().should_mutate(path):
            yield path
