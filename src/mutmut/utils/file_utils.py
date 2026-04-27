"""
File utilities for mutmut.

This module contains functions for walking source files in the workspace
and managing the mutants directory structure.
"""

import os
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from os import walk
from os.path import isdir
from os.path import isfile
from pathlib import Path

from mutmut.configuration import config


@contextmanager
def change_cwd(path: Path | str) -> Iterator[None]:
    old_cwd = Path(os.getcwd()).resolve()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def walk_all_files() -> Iterator[tuple[str, str]]:
    """Walk all files in configured paths_to_mutate.

    Yields:
        Tuples of (root_directory, filename) for each file found.
    """
    for path in config().source_paths:
        if not isdir(path):
            if isfile(path):
                yield "", str(path)
                continue
        for root, _, files in walk(path):
            for filename in files:
                yield root, filename


def walk_source_files() -> Iterator[Path]:
    """Walk all Python source files in configured paths_to_mutate.

    Yields:
        Path objects for each .py file found.
    """
    for root, filename in walk_all_files():
        if filename.endswith(".py"):
            yield Path(root) / filename


def walk_mutatable_files() -> Iterator[Path]:
    for path in walk_source_files():
        if config().should_mutate(path):
            yield path


def copy_src_dir() -> None:
    """Copy source directories to the mutants directory."""
    for path in config().source_paths:
        output_path: Path = Path("mutants") / path
        if isdir(path):
            shutil.copytree(path, output_path, dirs_exist_ok=True)
        else:
            output_path.parent.mkdir(exist_ok=True, parents=True)
            # copy mtime, so we later know that when source_mtime == target_mtime, the file is not (yet) mutated.
            shutil.copy2(path, output_path)


def copy_also_copy_files() -> None:
    """Copy additional files specified in config to the mutants directory."""
    assert isinstance(config().also_copy, list)
    for path in config().also_copy:
        print("     also copying", path)
        path = Path(path)
        destination = Path("mutants") / path
        if not path.exists():
            continue
        if path.is_file():
            shutil.copy(path, destination)
        else:
            shutil.copytree(path, destination, dirs_exist_ok=True)


def setup_source_paths() -> None:
    """Set up sys.path so mutated source code is imported instead of original.

    This ensures that:
    1. The mutated source code can be imported by the tests
    2. The original code CANNOT be imported by the tests
    """
    # ensure that the mutated source code can be imported by the tests
    source_code_paths = [Path("."), Path("src"), Path("source")]
    for path in source_code_paths:
        mutated_path = Path("mutants") / path
        if mutated_path.exists():
            sys.path.insert(0, str(mutated_path.absolute()))

    # ensure that the original code CANNOT be imported by the tests
    for path in source_code_paths:
        for i in range(len(sys.path)):
            while i < len(sys.path) and Path(sys.path[i]).resolve() == path.resolve():
                del sys.path[i]
