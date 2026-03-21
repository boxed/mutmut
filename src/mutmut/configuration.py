from __future__ import annotations

import fnmatch
import os
import platform
import sys
import warnings
from collections.abc import Callable
from configparser import ConfigParser
from configparser import NoOptionError
from configparser import NoSectionError
from dataclasses import dataclass
from enum import Enum
from os.path import isdir
from os.path import isfile
from pathlib import Path
from typing import Any


class ProcessIsolation(str, Enum):
    """Valid values for process_isolation config.

    Using str, Enum allows direct string comparison while providing
    validation and IDE support.
    """

    FORK = "fork"  # Default: current behavior
    HOT_FORK = "hot-fork"  # Fork-safe for gevent/grpc


class HotForkWarmup(str, Enum):
    """Warmup strategies for hot-fork orchestrator.

    Controls what the orchestrator does before forking grandchildren:
    - COLLECT: Run pytest --collect-only to pre-load test infrastructure (DEFAULT)
    - IMPORT: Import modules from a file (useful when test collection has side effects)
    - NONE: Just import pytest, no test collection
    """

    COLLECT = "collect"
    IMPORT = "import"
    NONE = "none"


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
        elif isinstance(default, float):
            return float(result)
        elif isinstance(default, int):
            return int(result)
        return result

    return setup_cfg_conf


def _guess_source_paths() -> list[str]:
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
        'Please specify it by adding "source_paths=code_dir" in setup.cfg to the [mutmut] section.'
    )


def _load_config() -> Config:
    s = _config_reader()

    paths_to_mutate = [Path(path) for path in s("paths_to_mutate", [])]
    if paths_to_mutate:
        warnings.warn("The config paths_to_mutate is deprecated. Please rename it to source_paths")
    source_paths = [Path(path) for path in s("source_paths", [])]
    source_paths = source_paths or paths_to_mutate or [Path(path) for path in _guess_source_paths()]

    tests_dir = s("tests_dir", [])
    if tests_dir:
        warnings.warn(
            "The config tests_dir is deprecated. Please add the path to pytest_add_cli_args_test_selection instead"
        )
    pytest_add_cli_args_test_selection = s("pytest_add_cli_args_test_selection", []) + tests_dir

    only_mutate = s("only_mutate", [])
    do_not_mutate = s("do_not_mutate", [])
    # only patterns for python files are valid: must end with ".py" or "*"
    invalid_patterns = [p for p in only_mutate + do_not_mutate if not (p.endswith("*") or p.endswith(".py"))]
    if invalid_patterns:
        warnings.warn(
            f'The configs only_mutate and do_not_mutate expect glob patterns like "src/api/*" or "src/main.py". Following patterns are likely invalid: {invalid_patterns}'
        )

    isolation_str = s("process_isolation", "fork")
    try:
        process_isolation = ProcessIsolation(isolation_str)
    except ValueError:
        valid = [e.value for e in ProcessIsolation]
        raise ValueError(f"Invalid process_isolation value: {isolation_str!r}. Expected one of: {valid}") from None

    # Validate hot_fork_warmup (default: collect)
    warmup_str = s("hot_fork_warmup", "collect")
    try:
        hot_fork_warmup = HotForkWarmup(warmup_str)
    except ValueError:
        valid = [e.value for e in HotForkWarmup]
        raise ValueError(f"Invalid hot_fork_warmup value: {warmup_str!r}. Expected one of: {valid}") from None

    return Config(
        only_mutate=only_mutate,
        do_not_mutate=do_not_mutate,
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
        source_paths=source_paths,
        pytest_add_cli_args=s("pytest_add_cli_args", []),
        pytest_add_cli_args_test_selection=pytest_add_cli_args_test_selection,
        timeout_multiplier=s("timeout_multiplier", 15.0),
        timeout_constant=s("timeout_constant", 1.0),
        type_check_command=s("type_check_command", []),
        use_setproctitle=s(
            "use_setproctitle", not platform.system() == "Darwin"
        ),  # False on Mac, true otherwise as default (https://github.com/boxed/mutmut/pull/450#issuecomment-4002571055)
        track_dependencies=s("track_dependencies", True),
        dependency_tracking_depth=s("dependency_tracking_depth", None),
        process_isolation=process_isolation,
        max_orchestrator_restarts=s("max_orchestrator_restarts", 3),
        hot_fork_warmup=hot_fork_warmup,
        preload_modules_file=s("preload_modules_file", None),
    )


@dataclass
class Config:
    also_copy: list[Path]
    only_mutate: list[str]
    do_not_mutate: list[str]
    max_stack_depth: int
    debug: bool
    source_paths: list[Path]
    pytest_add_cli_args: list[str]
    pytest_add_cli_args_test_selection: list[str]
    mutate_only_covered_lines: bool
    timeout_multiplier: float
    timeout_constant: float
    type_check_command: list[str]
    use_setproctitle: bool
    track_dependencies: bool
    dependency_tracking_depth: int | None
    process_isolation: ProcessIsolation
    max_orchestrator_restarts: int
    hot_fork_warmup: HotForkWarmup
    preload_modules_file: str | None

    def should_mutate(self, path: Path | str) -> bool:
        return self._should_include_for_mutation(path) and not self._should_ignore_for_mutation(path)

    def _should_include_for_mutation(self, path: Path | str) -> bool:
        if not self.only_mutate:
            return True
        path_str = str(path)
        if not path_str.endswith(".py"):
            return True
        for p in self.only_mutate:
            if fnmatch.fnmatch(path_str, p):
                return True
        return False

    def _should_ignore_for_mutation(self, path: Path | str) -> bool:
        path_str = str(path)
        if not path_str.endswith(".py"):
            return True
        for p in self.do_not_mutate:
            if fnmatch.fnmatch(path_str, p):
                return True
        return False

    @staticmethod
    def reset() -> None:
        global _config
        _config = None


_config: Config | None = None


class MutmutProgrammaticFailException(Exception):
    pass


def config() -> Config:
    """Get the global configuration singleton, creating it if needed."""
    global _config
    if _config is None:
        _config = _load_config()
    return _config


def reset_config() -> None:
    """Reset the global configuration. Primarily used for testing."""
    global _config
    _config = None
