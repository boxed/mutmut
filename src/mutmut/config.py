from __future__ import annotations

import fnmatch
import sys
import tomllib
from configparser import (
    ConfigParser,
    NoOptionError,
    NoSectionError,
)
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, TypeVar, cast

import mutmut

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")


@dataclass
class Config:
    also_copy: list[Path]
    do_not_mutate: list[str]
    max_stack_depth: int
    debug: bool
    paths_to_mutate: list[Path]
    pytest_add_cli_args: list[str]
    pytest_add_cli_args_test_selection: list[str]
    tests_dir: list[str]
    mutate_only_covered_lines: bool

    def should_ignore_for_mutation(self, path: Path | str) -> bool:
        checked_path = str(path)
        if not checked_path.endswith(".py"):
            return True
        return any(fnmatch.fnmatch(checked_path, pattern) for pattern in self.do_not_mutate)


DEFAULT_DEBUG = False
DEFAULT_MUTATE_ONLY_COVERED_LINES = False


def guess_paths_to_mutate() -> list[Path]:
    """Guess the path to source code to mutate."""
    this_dir = Path.cwd().name
    candidate_dirs = [
        "lib",
        "src",
        this_dir,
        this_dir.replace("-", "_"),
        this_dir.replace(" ", "_"),
        this_dir.replace("-", ""),
        this_dir.replace(" ", ""),
    ]
    seen: set[str] = set()
    for candidate in candidate_dirs:
        if candidate in seen:
            continue
        seen.add(candidate)
        if Path(candidate).is_dir():
            return [Path(candidate)]

    file_candidate = Path(f"{this_dir}.py")
    if file_candidate.is_file():
        return [file_candidate]

    msg = (
        "Could not figure out where the code to mutate is. "
        'Please specify it by adding "paths_to_mutate=code_dir" in setup.cfg to the [mutmut] section.'
    )
    raise FileNotFoundError(msg)


def config_reader() -> Callable[[str, T], T]:
    path = Path("pyproject.toml")
    if path.exists():
        data = tomllib.loads(path.read_text("utf-8"))

        try:
            config = data["tool"]["mutmut"]
        except KeyError:
            pass
        else:

            def reader(key: str, default: T) -> T:
                try:
                    result: Any = config[key]
                except KeyError:
                    return default
                return cast("T", result)

            return reader

    config_parser = ConfigParser()
    config_parser.read("setup.cfg")

    def reader(key: str, default: T) -> T:
        try:
            result = config_parser.get("mutmut", key)
        except (NoOptionError, NoSectionError):
            return default
        if isinstance(default, list):
            result = [x for x in result.split("\n") if x] if "\n" in result else [result]
        elif isinstance(default, bool):
            result = result.lower() in {"1", "t", "true"}
        elif isinstance(default, int):
            result = int(result)
        return cast("T", result)

    return reader


def ensure_config_loaded() -> None:
    if mutmut.config is None or isinstance(mutmut.config, ModuleType):
        mutmut.config = load_config()


def get_config() -> Config:
    ensure_config_loaded()
    config = mutmut.config
    if config is None:
        msg = "mutmut config must be loaded before accessing it"
        raise RuntimeError(msg)
    return config


def load_config() -> Config:
    reader: Any = config_reader()

    paths_from_config = [Path(y) for y in reader("paths_to_mutate", [])]

    return Config(
        do_not_mutate=reader("do_not_mutate", []),
        also_copy=[Path(y) for y in reader("also_copy", [])]
        + [
            Path("tests/"),
            Path("test/"),
            Path("setup.cfg"),
            Path("pyproject.toml"),
        ]
        + list(Path().glob("test*.py")),
        max_stack_depth=reader("max_stack_depth", -1),
        debug=reader("debug", DEFAULT_DEBUG),
        mutate_only_covered_lines=reader("mutate_only_covered_lines", DEFAULT_MUTATE_ONLY_COVERED_LINES),
        paths_to_mutate=paths_from_config or guess_paths_to_mutate(),
        tests_dir=reader("tests_dir", []),
        pytest_add_cli_args=reader("pytest_add_cli_args", []),
        pytest_add_cli_args_test_selection=reader("pytest_add_cli_args_test_selection", []),
    )


class _ConfigModule(ModuleType):
    @staticmethod
    def _config_obj() -> Config | None:
        cfg = getattr(mutmut, "config", None)
        if isinstance(cfg, ModuleType):
            return None
        return cast("Config | None", cfg)

    def __getattr__(self, name: str) -> object:
        cfg = self._config_obj()
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: object) -> None:
        if name in self.__dict__ or hasattr(type(self), name):
            super().__setattr__(name, value)
            return
        cfg = self._config_obj()
        if cfg is not None and hasattr(cfg, name):
            setattr(cfg, name, value)
            return
        super().__setattr__(name, value)


_module = sys.modules[__name__]
setattr(mutmut, "config_module", _module)  # noqa: B010
if isinstance(getattr(mutmut, "config", None), ModuleType):
    mutmut.config = None
_module.__class__ = _ConfigModule
