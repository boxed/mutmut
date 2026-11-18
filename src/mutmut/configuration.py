from __future__ import annotations

import fnmatch
import hashlib
import os
import platform
import sys
import warnings
from collections.abc import Callable
from configparser import ConfigParser
from configparser import NoOptionError
from configparser import NoSectionError
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from os.path import isdir
from os.path import isfile
from pathlib import Path
from typing import Any

from mutmut.mutation.mutators import mutation_type_names


def _mutation_type_matches(configured_type: str, mutation_type: str) -> bool:
    return mutation_type == configured_type or mutation_type.startswith(f"{configured_type}.")


def _validate_mutation_types(configured_types: list[str]) -> None:
    invalid_types = [
        configured_type
        for configured_type in configured_types
        if not any(_mutation_type_matches(configured_type, mutation_type) for mutation_type in mutation_type_names)
    ]
    if invalid_types:
        available_types = ", ".join(sorted(mutation_type_names))
        raise ValueError(
            f"Unknown mutation type(s): {', '.join(invalid_types)}. Available mutation types: {available_types}"
        )


class ProcessIsolation(str, Enum):
    """Valid values for the ``process_isolation`` config.

    Chooses *which process* each mutant worker is forked from. Named after the
    ``multiprocessing`` start methods of the same name, which make the same
    distinction:

    - FORK: fork straight from mutmut's main process, which has already imported
      pytest and run the suite to collect stats. Fastest, but every worker
      inherits whatever the test setup left in that process.
    - FORKSERVER: keep the main process free of pytest and fork a dedicated
      server process that does nothing but import and fork workers. For test
      setups that are not fork-safe (gevent, grpc, torch).
    - SPAWN: start a fresh Python process per mutant. Slowest, but the only one
      that works without ``os.fork``, so it is the default on Windows.

    Subclassing ``str`` allows direct string comparison while still giving us
    validation and IDE support.
    """

    FORK = "fork"
    FORKSERVER = "forkserver"
    SPAWN = "spawn"


class ForkServerWarmup(str, Enum):
    """Warmup strategy for the fork server.

    Controls what the fork server does after importing the test runner but
    before forking any grandchildren:

    - COLLECT: run ``pytest --collect-only`` to pre-load conftest, plugins, and
      test modules (default; biggest speedup for most projects).
    - IMPORT: import the modules listed in ``preload_modules`` and in
      ``preload_modules_file`` (useful when
      test collection has side effects you do not want shared).
    - NONE: import nothing extra beyond what running a test needs.
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
    config_parser.read("setup.cfg", encoding="utf-8")

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


def _parse_mutants_dir(raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Invalid mutants_dir value: must be a non-empty path.")
    mutants_dir = Path(raw)
    cwd = Path.cwd().resolve()
    resolved = (cwd / mutants_dir).resolve()
    if cwd.is_relative_to(resolved):
        raise ValueError("Invalid mutants_dir value: must not be the project root or an ancestor directory.")
    return mutants_dir


def _validate_mutants_dir_overlap(mutants_dir: Path, source_paths: list[Path], also_copy: list[Path]) -> None:
    cwd = Path.cwd().resolve()
    resolved_mutants = (cwd / mutants_dir).resolve()
    for entry in [*source_paths, *also_copy]:
        resolved_entry = (cwd / entry).resolve()
        if resolved_entry == cwd:
            continue
        if resolved_mutants.is_relative_to(resolved_entry) or resolved_entry.is_relative_to(resolved_mutants):
            raise ValueError(f"Invalid mutants_dir value: {mutants_dir} must not overlap configured path {entry}.")


def _load_config() -> Config:
    s = _config_reader()

    paths_to_mutate = [Path(path) for path in s("paths_to_mutate", [])]
    if paths_to_mutate:
        warnings.warn("The config paths_to_mutate is deprecated. Please rename it to source_paths")
    source_paths = [Path(path) for path in s("source_paths", [])]
    source_paths = source_paths or paths_to_mutate or [Path(path) for path in _guess_source_paths()]

    mutants_dir = _parse_mutants_dir(s("mutants_dir", "mutants"))
    resolved_mutants = (Path.cwd().resolve(strict=True) / mutants_dir).resolve()

    # We resolve at startup, s.t. we are still in the current working directory (and no tests modified the directory)
    resolved_mutated_source_paths = [(resolved_mutants / p).resolve() for p in source_paths]

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

    disable_mutation_types = s("disable_mutation_types", [])
    _validate_mutation_types(disable_mutation_types)

    isolation_str = s("process_isolation", "spawn" if sys.platform == "win32" else "fork")
    try:
        process_isolation = ProcessIsolation(isolation_str)
    except ValueError:
        valid = [e.value for e in ProcessIsolation]
        raise ValueError(f"Invalid process_isolation value: {isolation_str!r}. Expected one of: {valid}") from None
    if sys.platform == "win32" and process_isolation != ProcessIsolation.SPAWN:
        # A pyproject.toml shared with POSIX users must keep working here, so fall back instead of failing.
        warnings.warn(f'process_isolation = "{isolation_str}" needs os.fork, which Windows lacks. Using "spawn".')
        process_isolation = ProcessIsolation.SPAWN

    warmup_str = s("forkserver_warmup", "collect")
    try:
        forkserver_warmup = ForkServerWarmup(warmup_str)
    except ValueError:
        valid = [e.value for e in ForkServerWarmup]
        raise ValueError(f"Invalid forkserver_warmup value: {warmup_str!r}. Expected one of: {valid}") from None

    also_copy = (
        [Path(y) for y in s("also_copy", [])]
        + [
            Path("tests/"),
            Path("test/"),
            Path("setup.cfg"),
            Path("pyproject.toml"),
            Path("uv.lock"),
            Path("poetry.lock"),
            Path("Pipfile.lock"),
            Path("pdm.lock"),
        ]
        + list(Path(".").glob("test*.py"))
    )
    _validate_mutants_dir_overlap(mutants_dir, source_paths, also_copy)

    return Config(
        only_mutate=only_mutate,
        do_not_mutate=do_not_mutate,
        do_not_mutate_patterns=s("do_not_mutate_patterns", []),
        also_copy=also_copy,
        max_stack_depth=s("max_stack_depth", -1),
        debug=s("debug", False),
        mutate_only_covered_lines=s("mutate_only_covered_lines", False),
        source_paths=source_paths,
        resolved_mutated_source_paths=resolved_mutated_source_paths,
        pytest_add_cli_args=s("pytest_add_cli_args", []),
        pytest_add_cli_args_test_selection=pytest_add_cli_args_test_selection,
        timeout_multiplier=s("timeout_multiplier", 15.0),
        timeout_constant=s("timeout_constant", 1.0),
        type_check_command=s("type_check_command", []),
        use_setproctitle=s(
            "use_setproctitle", not platform.system() == "Darwin"
        ),  # False on Mac, true otherwise as default (https://github.com/boxed/mutmut/pull/450#issuecomment-4002571055)
        track_dependencies=s("track_dependencies", True),
        dependency_tracking_depth=s("dependency_tracking_depth", -1),
        cache_invalidation_files=s("cache_invalidation_files", []),
        cache_invalidation_exclude=s("cache_invalidation_exclude", []),
        on_dependency_change=s("on_dependency_change", "warn"),
        use_git_change_detection=s("use_git_change_detection", True),
        process_isolation=process_isolation,
        forkserver_warmup=forkserver_warmup,
        max_forkserver_restarts=s("max_forkserver_restarts", 3),
        preload_modules=s("preload_modules", []),
        preload_modules_file=s("preload_modules_file", None),
        log_to_file=s("log_to_file", False),
        log_file_path=s("log_file_path", str(mutants_dir / "mutmut-debug.log")),
        mutants_dir=mutants_dir,
        disable_mutation_types=disable_mutation_types,
    )


_config: Config | None = None


@dataclass
class Config:
    also_copy: list[Path]
    only_mutate: list[str]
    do_not_mutate: list[str]
    do_not_mutate_patterns: list[str]
    max_stack_depth: int
    debug: bool
    source_paths: list[Path]
    resolved_mutated_source_paths: list[Path]
    pytest_add_cli_args: list[str]
    pytest_add_cli_args_test_selection: list[str]
    mutate_only_covered_lines: bool
    timeout_multiplier: float
    timeout_constant: float
    type_check_command: list[str]
    use_setproctitle: bool
    track_dependencies: bool
    dependency_tracking_depth: int
    cache_invalidation_files: list[str]
    cache_invalidation_exclude: list[str]
    on_dependency_change: str
    use_git_change_detection: bool
    process_isolation: ProcessIsolation
    forkserver_warmup: ForkServerWarmup
    max_forkserver_restarts: int
    preload_modules_file: str | None
    log_to_file: bool
    log_file_path: str
    mutants_dir: Path = Path("mutants")
    disable_mutation_types: list[str] = field(default_factory=list)
    preload_modules: list[str] = field(default_factory=list)

    def config_fingerprint(self) -> dict[str, str]:
        """Hash the config fields that can change cached mutant *results*, grouped so the
        caller can invalidate only the verdict classes each group can affect.

        Fields that only change *which* mutants exist (source_paths, only_mutate, etc.)
        are deliberately excluded: new mutants are born uncached and dropped ones simply
        stop being walked, so they need no result invalidation.
        """

        def _hash(value: object) -> str:
            return hashlib.sha256(repr(value).encode()).hexdigest()[:12]

        return {
            # global pytest behaviour: a change can flip any verdict
            "test_execution": _hash(tuple(self.pytest_add_cli_args)),
            # which tests cover which function: a change reshapes the stats mapping
            "test_selection": _hash(tuple(self.pytest_add_cli_args_test_selection)),
            # only reclassifies timeouts
            "timeout": _hash((self.timeout_multiplier, self.timeout_constant)),
            # only changes the type-check pre-filter
            "type_check": _hash(tuple(self.type_check_command)),
            # Filtering changes mutant numbering, so no cached verdict is safe to reuse.
            "mutant_generation": _hash(tuple(self.disable_mutation_types)),
        }

    def should_mutate_type(self, mutation_type: str) -> bool:
        return not any(
            _mutation_type_matches(disabled_type, mutation_type) for disabled_type in self.disable_mutation_types
        )

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


def config() -> Config:
    global _config
    if _config is None:
        _config = _load_config()
    return _config


def get_mutants_dir() -> Path:
    """Return the configured mutants directory without requiring source_paths to resolve."""
    if _config is not None:
        return _config.mutants_dir
    return _parse_mutants_dir(_config_reader()("mutants_dir", "mutants"))


def reset_config() -> None:
    global _config
    _config = None
