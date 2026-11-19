from __future__ import annotations

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
    for path in config().source_paths:
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
    cfg = config()
    for path in walk_source_files():
        if cfg.should_mutate(path):
            yield path


def copy_src_dir() -> None:
    for root, name in walk_all_files():
        source_path = Path(root) / name
        target_path = Path("mutants") / root / name

        if target_path.exists():
            continue

        if isdir(source_path):
            shutil.copytree(source_path, target_path)
        else:
            target_path.parent.mkdir(exist_ok=True, parents=True)
            # copy mtime, so we later know that when source_mtime == target_mtime, the file is not (yet) mutated.
            shutil.copy2(source_path, target_path)


def copy_also_copy_files() -> None:
    assert isinstance(config().also_copy, list)
    for path in config().also_copy:
        print("     also copying", path)
        path = Path(path)
        destination = Path("mutants") / path
        if not path.exists():
            continue
        if path.is_file():
            shutil.copy2(path, destination)
        else:
            shutil.copytree(path, destination, dirs_exist_ok=True)
            remove_files_missing_from_source(path, destination)


def _overlaps_source_paths(path: Path) -> bool:
    resolved = path.resolve()
    for source_path in config().source_paths:
        source = Path(source_path).resolve()
        if resolved == source or source in resolved.parents or resolved in source.parents:
            return True
    return False


def remove_files_missing_from_source(source: Path, destination: Path) -> None:
    """Remove files from the mutants/ copy that were deleted in the project.

    copytree with dirs_exist_ok never deletes anything, so a deleted test module would
    otherwise keep running from mutants/. __pycache__ is left alone, and source paths
    are skipped because mutants/ has mutmut's own files there.
    """
    if _overlaps_source_paths(source):
        return
    for root, dirs, files in walk(destination, topdown=False):
        root_path = Path(root)
        if "__pycache__" in root_path.relative_to(destination).parts:
            continue
        relative_root = root_path.relative_to(destination)
        for name in files:
            if not (source / relative_root / name).exists():
                (root_path / name).unlink()
        for name in dirs:
            copied_dir = root_path / name
            if name != "__pycache__" and not (source / relative_root / name).exists():
                shutil.rmtree(copied_dir)


def setup_source_paths() -> None:
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
