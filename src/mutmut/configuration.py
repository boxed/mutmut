from __future__ import annotations

import fnmatch
import os
import sys
from collections.abc import Callable
from configparser import ConfigParser
from configparser import NoOptionError
from configparser import NoSectionError
from dataclasses import dataclass
from os.path import isdir
from os.path import isfile
from pathlib import Path
from typing import Any


def _config_reader() -> Callable[[str, Any], Any]:
    path = Path("pyproject.toml")
    if path.exists():
        if sys.version_info >= (3, 11):
            from tomllib import loads
        else:
            # noinspection PyPackageRequirements
            from toml import loads
        data = loads(path.read_text("utf-8"))

        try:
            config = data["tool"]["mutmut"]
        except KeyError:
            pass
        else:

            def toml_conf(key: str, default: Any) -> Any:
                try:
                    result = config[key]
                except KeyError:
                    return default
                return result

            return toml_conf

    config_parser = ConfigParser()
    config_parser.read("setup.cfg")

    def setup_cfg_conf(key: str, default: Any) -> Any:
        try:
            result = config_parser.get("mutmut", key)
        except (NoOptionError, NoSectionError):
            return default
        if isinstance(default, list):
            if "\n" in result:
                return [x for x in result.split("\n") if x]
            else:
                return [result]
        elif isinstance(default, bool):
            return result.lower() in ("1", "t", "true")
        elif isinstance(default, int):
            return int(result)
        return result

    return setup_cfg_conf


def _guess_paths_to_mutate() -> list[str]:
    """Guess the path to source code to mutate

    :rtype: str
    """
    this_dir = os.getcwd().split(os.sep)[-1]
    if isdir("lib"):
        return ["lib"]
    elif isdir("src"):
        return ["src"]
    elif isdir(this_dir):
        return [this_dir]
    elif isdir(this_dir.replace("-", "_")):
        return [this_dir.replace("-", "_")]
    elif isdir(this_dir.replace(" ", "_")):
        return [this_dir.replace(" ", "_")]
    elif isdir(this_dir.replace("-", "")):
        return [this_dir.replace("-", "")]
    elif isdir(this_dir.replace(" ", "")):
        return [this_dir.replace(" ", "")]
    if isfile(this_dir + ".py"):
        return [this_dir + ".py"]
    raise FileNotFoundError(
        "Could not figure out where the code to mutate is. "
        'Please specify it by adding "paths_to_mutate=code_dir" in setup.cfg to the [mutmut] section.'
    )


def _load_config() -> Config:
    s = _config_reader()

    return Config(
        do_not_mutate=s("do_not_mutate", []),
        also_copy=[Path(y) for y in s("also_copy", [])]
        + [
            Path("tests/"),
            Path("test/"),
            Path("setup.cfg"),
            Path("pyproject.toml"),
        ]
        + list(Path(".").glob("test*.py")),
        max_stack_depth=s("max_stack_depth", -1),
        debug=s("debug", False),
        mutate_only_covered_lines=s("mutate_only_covered_lines", False),
        paths_to_mutate=[Path(y) for y in s("paths_to_mutate", [])] or [Path(p) for p in _guess_paths_to_mutate()],
        tests_dir=s("tests_dir", []),
        pytest_add_cli_args=s("pytest_add_cli_args", []),
        pytest_add_cli_args_test_selection=s("pytest_add_cli_args_test_selection", []),
        type_check_command=s("type_check_command", []),
    )


_config: Config | None = None


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
    type_check_command: list[str]

    def should_ignore_for_mutation(self, path: Path | str) -> bool:
        path_str = str(path)
        if not path_str.endswith(".py"):
            return True
        for p in self.do_not_mutate:
            if fnmatch.fnmatch(path_str, p):
                return True
        return False

    @staticmethod
    def ensure_loaded() -> None:
        global _config
        if _config is None:
            _config = _load_config()

    @staticmethod
    def get() -> Config:
        global _config
        Config.ensure_loaded()
        assert _config is not None
        return _config

    @staticmethod
    def reset() -> None:
        global _config
        _config = None
