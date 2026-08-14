from __future__ import annotations

from abc import ABC
from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING
from typing import Any

from mutmut.configuration import HotForkWarmup
from mutmut.configuration import config
from mutmut.state import state
from mutmut.stats import save_stats
from mutmut.utils.file_utils import change_cwd
from mutmut.utils.format_utils import strip_prefix

if TYPE_CHECKING:
    from coverage import Coverage


class CollectTestsFailedException(Exception):
    pass


class BadTestExecutionCommandsException(Exception):
    def __init__(self, pytest_args: list[str]) -> None:
        msg = f"Failed to run pytest with args: {pytest_args}. If your config sets debug=true, the original pytest error should be above."
        super().__init__(msg)


def unused(*_: object) -> None:
    pass


class TestRunner(ABC):
    def run_stats(self, *, tests: Iterable[str]) -> int:
        raise NotImplementedError()

    def run_forced_fail(self) -> int:
        raise NotImplementedError()

    def prepare_main_test_run(self) -> None:
        pass

    def run_tests(self, *, mutant_name: str | None, tests: Iterable[str]) -> int:
        raise NotImplementedError()

    def collect_main_test_coverage(self, cov: Coverage) -> int:
        raise NotImplementedError()

    def list_all_tests(self) -> ListAllTestsResult:
        raise NotImplementedError()

    def warm_up(self) -> None:
        """Pre-import expensive modules so forked children inherit them.

        Called by HotForkRunner inside the orchestrator after the test runner is
        created. Importing pytest (and optionally running collection) here means
        the grandchildren fork with everything already in memory. The default is
        a no-op for runners that do not benefit from it.
        """
        return


def collected_test_names() -> set[str]:
    return set(state().duration_by_test.keys())


class ListAllTestsResult:
    def __init__(self, *, ids: set[str]) -> None:
        assert isinstance(ids, set)
        self.ids = ids

    def clear_out_obsolete_test_names(self) -> None:
        count_before = sum(len(x) for x in state().tests_by_mangled_function_name)
        state().tests_by_mangled_function_name = defaultdict(
            set,
            **{
                k: {test_name for test_name in test_names if test_name in self.ids}
                for k, test_names in state().tests_by_mangled_function_name.items()
            },
        )
        count_after = sum(len(x) for x in state().tests_by_mangled_function_name)
        if count_before != count_after:
            print(f"Removed {count_before - count_after} obsolete test names")
            save_stats()

    def new_tests(self) -> set[str]:
        return self.ids - collected_test_names()


class PytestRunner(TestRunner):
    def __init__(self) -> None:
        self._pytest_add_cli_args: list[str] = config().pytest_add_cli_args
        self._pytest_add_cli_args_test_selection: list[str] = config().pytest_add_cli_args_test_selection

    def warm_up(self) -> None:
        """Pre-load test infrastructure per the ``hot_fork_warmup`` config.

        - COLLECT (default): run ``pytest --collect-only`` to import conftest,
          plugins, and test modules (biggest speedup for most projects).
        - IMPORT: import the modules listed in ``preload_modules_file``.
        - NONE: import nothing beyond what running a test already needs.
        """
        warmup = config().hot_fork_warmup

        if warmup == HotForkWarmup.COLLECT:
            with change_cwd("mutants"):
                self.execute_pytest(["--collect-only", "-qqq"] + self._pytest_add_cli_args_test_selection)
        elif warmup == HotForkWarmup.IMPORT:
            preload_file = config().preload_modules_file
            if preload_file:
                import importlib

                with open(preload_file) as f:
                    for line in f:
                        module_name = line.strip()
                        if module_name and not module_name.startswith("#"):
                            try:
                                importlib.import_module(module_name)
                            except ImportError:
                                pass  # Best effort.
        # HotForkWarmup.NONE -> no-op.

    # noinspection PyMethodMayBeStatic
    def execute_pytest(self, params: list[str], **kwargs: Any) -> int:
        import pytest

        params = ["--rootdir=.", "--tb=native"] + params + self._pytest_add_cli_args
        if config().debug:
            params = ["-vv"] + params
            print("python -m pytest ", " ".join([f'"{param}"' for param in params]))
        exit_code = int(pytest.main(params, **kwargs))
        if config().debug:
            print("    exit code", exit_code)
        if exit_code == 4:
            raise BadTestExecutionCommandsException(params)
        return exit_code

    def _pytest_args_regular_run(self, tests: Iterable[str]) -> list[str]:
        pytest_args = ["-x", "-q", "-p", "no:randomly", "-p", "no:random-order"]
        if tests:
            pytest_args += list(tests)
        else:
            pytest_args += self._pytest_add_cli_args_test_selection
        return pytest_args

    def run_stats(self, *, tests: Iterable[str]) -> int:
        class StatsCollector:
            # noinspection PyMethodMayBeStatic
            def pytest_runtest_logstart(self, nodeid: str, location: Any) -> None:
                state().duration_by_test[nodeid] = 0

            # noinspection PyMethodMayBeStatic
            def pytest_runtest_teardown(self, item: Any, nextitem: Any) -> None:
                unused(nextitem)
                for function in state()._stats:
                    state().tests_by_mangled_function_name[function].add(strip_prefix(item._nodeid, prefix="mutants/"))
                state()._stats.clear()

            # noinspection PyMethodMayBeStatic
            def pytest_runtest_makereport(self, item: Any, call: Any) -> None:
                if call.when != "call":
                    return
                state().duration_by_test[item.nodeid] += call.duration

        stats_collector = StatsCollector()

        with change_cwd("mutants"):
            return int(self.execute_pytest(self._pytest_args_regular_run(tests), plugins=[stats_collector]))

    def run_tests(self, *, mutant_name: str | None, tests: Iterable[str]) -> int:
        with change_cwd("mutants"):
            return int(self.execute_pytest(self._pytest_args_regular_run(tests)))

    def collect_main_test_coverage(self, cov: Coverage) -> int:
        with change_cwd("mutants"), cov.collect():
            self.prepare_main_test_run()
            return int(self.execute_pytest(self._pytest_args_regular_run([])))

    def run_forced_fail(self) -> int:
        return self.run_tests(mutant_name=None, tests=[])

    def list_all_tests(self) -> ListAllTestsResult:
        class TestsCollector:
            def __init__(self) -> None:
                self.collected_nodeids: set[str] = set()
                self.deselected_nodeids: set[str] = set()

            def pytest_collection_modifyitems(self, items: Any) -> None:
                self.collected_nodeids |= {item.nodeid for item in items}

            def pytest_deselected(self, items: Any) -> None:
                self.deselected_nodeids |= {item.nodeid for item in items}

        collector = TestsCollector()

        pytest_args = ["-x", "-q", "--collect-only"] + self._pytest_add_cli_args_test_selection

        with change_cwd("mutants"):
            exit_code = int(self.execute_pytest(pytest_args, plugins=[collector]))
            if exit_code != 0:
                raise CollectTestsFailedException()

        selected_nodeids = collector.collected_nodeids - collector.deselected_nodeids
        return ListAllTestsResult(ids=selected_nodeids)


class HammettRunner(TestRunner):
    def __init__(self) -> None:
        self.hammett_kwargs: Any = None

    def run_stats(self, *, tests: Iterable[str]) -> int:
        import hammett

        print("Running hammett stats...")

        def post_test_callback(_name: str, **_: Any) -> None:
            for function in state()._stats:
                state().tests_by_mangled_function_name[function].add(_name)
            state()._stats.clear()

        return int(
            hammett.main(
                quiet=True,
                fail_fast=True,
                disable_assert_analyze=True,
                post_test_callback=post_test_callback,
                use_cache=False,
                insert_cwd=False,
            )
        )

    def run_forced_fail(self) -> int:
        import hammett

        return int(
            hammett.main(quiet=True, fail_fast=True, disable_assert_analyze=True, use_cache=False, insert_cwd=False)
        )

    def prepare_main_test_run(self) -> None:
        import hammett

        self.hammett_kwargs = hammett.main_setup(
            quiet=True,
            fail_fast=True,
            disable_assert_analyze=True,
            use_cache=False,
            insert_cwd=False,
        )

    def run_tests(self, *, mutant_name: str | None, tests: Iterable[str]) -> int:
        import hammett

        hammett.Config.workerinput = dict(workerinput=f"_{mutant_name}")
        return int(hammett.main_run_tests(**self.hammett_kwargs, tests=tests))
