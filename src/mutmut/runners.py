from __future__ import annotations

import importlib
import os
from abc import ABC, abstractmethod
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

import mutmut
from mutmut.config import get_config
from mutmut.meta import save_stats

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

PYTEST_USAGE_ERROR_EXIT_CODE = 4


class BadTestExecutionCommandsException(Exception):
    """The pytest invocation failed because the provided CLI args were invalid."""


class CollectTestsFailedException(Exception):
    """Pytest failed to collect tests."""


class PostTestCallback(Protocol):
    def __call__(self, name: str, **kwargs: object) -> None: ...


class HammettConfigProtocol(Protocol):
    workerinput: dict[str, str]


class HammettModule(Protocol):
    Config: HammettConfigProtocol

    def main(
        self,
        *,
        quiet: bool,
        fail_fast: bool,
        disable_assert_analyze: bool,
        post_test_callback: PostTestCallback | None = None,
        use_cache: bool,
        insert_cwd: bool,
    ) -> int: ...

    def main_setup(
        self,
        *,
        quiet: bool,
        fail_fast: bool,
        disable_assert_analyze: bool,
        use_cache: bool,
        insert_cwd: bool,
    ) -> dict[str, object]: ...

    def main_run_tests(self, *, tests: Iterable[str] | None, **kwargs: object) -> int: ...


class TestRunner(ABC):
    @abstractmethod
    def run_stats(self, *, tests: Iterable[str] | None) -> int:
        """Collect statistics for the provided tests."""

    @abstractmethod
    def run_forced_fail(self) -> int:
        """Run the forced-fail hook for the runner."""

    @abstractmethod
    def prepare_main_test_run(self) -> None:
        """Prepare the test runner before executing tests."""

    @abstractmethod
    def run_tests(self, *, mutant_name: str | None, tests: Iterable[str] | None) -> int:
        """Execute the provided tests for the given mutant."""

    @abstractmethod
    def list_all_tests(self) -> ListAllTestsResult:
        """Return all available tests."""


@contextmanager
def change_cwd(path: Path | str) -> Iterator[None]:
    old_cwd = Path(Path.cwd()).resolve()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def collected_test_names() -> set[str]:
    return set(mutmut.duration_by_test.keys())


class ListAllTestsResult:
    def __init__(self, *, ids: set[str]) -> None:
        if not isinstance(ids, set):
            msg = f"ids must be a set, got {type(ids)}"
            raise TypeError(msg)
        self.ids = ids

    def clear_out_obsolete_test_names(self) -> None:
        count_before = sum(len(v) for v in mutmut.tests_by_mangled_function_name.values())
        mutmut.tests_by_mangled_function_name = defaultdict(
            set,
            **{
                k: {test_name for test_name in test_names if test_name in self.ids}
                for k, test_names in mutmut.tests_by_mangled_function_name.items()
            },
        )
        count_after = sum(len(v) for v in mutmut.tests_by_mangled_function_name.values())
        if count_before != count_after:
            print(f"Removed {count_before - count_after} obsolete test names")
            save_stats()

    def new_tests(self) -> set[str]:
        return self.ids - collected_test_names()


def _normalized_nodeid(nodeid: str) -> str:
    prefix = "mutants/"
    if nodeid.startswith(prefix):
        return nodeid[len(prefix) :]
    return nodeid


class PytestRunner(TestRunner):
    def __init__(self):
        config = get_config()
        self._pytest_add_cli_args: list[str] = list(config.pytest_add_cli_args)
        self._pytest_add_cli_args_test_selection: list[str] = list(config.pytest_add_cli_args_test_selection)

        self._pytest_add_cli_args_test_selection += config.tests_dir

    def prepare_main_test_run(self) -> None:
        """Pytest does not need additional preparation."""

    def execute_pytest(self, params: list[str], **kwargs: Any) -> int:
        import pytest  # noqa: PLC0415

        config = get_config()
        params = ["--rootdir=.", "--tb=native", *params, *self._pytest_add_cli_args]
        if config.debug:
            params = ["-vv", *params]
            print("python -m pytest ", " ".join([f'"{param}"' for param in params]))
        exit_code = int(pytest.main(params, **kwargs))
        if config.debug:
            print("    exit code", exit_code)
        if exit_code == PYTEST_USAGE_ERROR_EXIT_CODE:
            raise BadTestExecutionCommandsException(params)
        return exit_code

    def run_stats(self, *, tests: Iterable[str] | None) -> int:
        class StatsCollector:
            def pytest_runtest_logstart(self, nodeid, location):  # noqa: PLR6301
                del location
                mutmut.duration_by_test[nodeid] = 0

            def pytest_runtest_teardown(self, item, nextitem):  # noqa: PLR6301
                del nextitem
                for function in mutmut.consume_stats():
                    mutmut.tests_by_mangled_function_name[function].add(
                        _normalized_nodeid(item.nodeid),
                    )

            def pytest_runtest_makereport(self, item, call):  # noqa: PLR6301
                mutmut.duration_by_test[item.nodeid] += call.duration

        stats_collector = StatsCollector()

        pytest_args = ["-x", "-q"]
        if tests:
            pytest_args += list(tests)
        else:
            pytest_args += self._pytest_add_cli_args_test_selection
        with change_cwd("mutants"):
            return int(self.execute_pytest(pytest_args, plugins=[stats_collector]))

    def run_tests(self, *, mutant_name: str | None, tests: Iterable[str] | None) -> int:
        del mutant_name
        pytest_args = ["-x", "-q", "-p", "no:randomly", "-p", "no:random-order"]
        if tests:
            pytest_args += list(tests)
        else:
            pytest_args += self._pytest_add_cli_args_test_selection
        with change_cwd("mutants"):
            return int(self.execute_pytest(pytest_args))

    def run_forced_fail(self) -> int:
        pytest_args = ["-x", "-q", *self._pytest_add_cli_args_test_selection]
        with change_cwd("mutants"):
            return int(self.execute_pytest(pytest_args))

    def list_all_tests(self) -> ListAllTestsResult:
        class TestsCollector:
            def __init__(self):
                self.collected_nodeids = set()
                self.deselected_nodeids = set()

            def pytest_collection_modifyitems(self, items):
                self.collected_nodeids |= {item.nodeid for item in items}

            def pytest_deselected(self, items):
                self.deselected_nodeids |= {item.nodeid for item in items}

        collector = TestsCollector()

        pytest_args = ["-x", "-q", "--collect-only", *self._pytest_add_cli_args_test_selection]

        with change_cwd("mutants"):
            exit_code = int(self.execute_pytest(pytest_args, plugins=[collector]))
            if exit_code != 0:
                raise CollectTestsFailedException

        selected_nodeids = collector.collected_nodeids - collector.deselected_nodeids
        return ListAllTestsResult(ids=selected_nodeids)


def import_hammett() -> HammettModule:
    module = importlib.import_module("hammett")
    return cast("HammettModule", module)


class HammettRunner(TestRunner):
    def __init__(self):
        self.hammett_kwargs: dict[str, object] | None = None

    def run_stats(self, *, tests: Iterable[str] | None) -> int:  # noqa: PLR6301
        del tests
        hammett = import_hammett()

        print("Running hammett stats...")

        def post_test_callback(_name: str, **_: object) -> None:
            for function in mutmut.consume_stats():
                mutmut.tests_by_mangled_function_name[function].add(_name)

        return hammett.main(
            quiet=True,
            fail_fast=True,
            disable_assert_analyze=True,
            post_test_callback=cast("PostTestCallback", post_test_callback),
            use_cache=False,
            insert_cwd=False,
        )

    def run_forced_fail(self) -> int:  # noqa: PLR6301
        hammett = import_hammett()

        return hammett.main(
            quiet=True,
            fail_fast=True,
            disable_assert_analyze=True,
            use_cache=False,
            insert_cwd=False,
        )

    def prepare_main_test_run(self) -> None:
        hammett = import_hammett()

        self.hammett_kwargs = hammett.main_setup(
            quiet=True,
            fail_fast=True,
            disable_assert_analyze=True,
            use_cache=False,
            insert_cwd=False,
        )

    def run_tests(self, *, mutant_name: str | None, tests: Iterable[str] | None) -> int:
        hammett = import_hammett()

        hammett.Config.workerinput = dict(workerinput=f"_{mutant_name}")
        kwargs = self.hammett_kwargs
        if kwargs is None:
            msg = "Hammett runner has not been prepared"
            raise RuntimeError(msg)
        return hammett.main_run_tests(**kwargs, tests=tests)
