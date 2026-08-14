from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from collections.abc import Iterable
from pathlib import Path
from threading import Lock
from typing import Any

from rich.text import Text

from mutmut.configuration import config
from mutmut.models.cache_status import CACHE_STATUS_EMOJI
from mutmut.models.cache_status import CacheStatus
from mutmut.mutation.data import SourceFileMutationData
from mutmut.mutation.file_mutation import compute_function_hashes
from mutmut.state import state
from mutmut.stats import Stat
from mutmut.stats import collect_stat
from mutmut.stats import emoji_by_status
from mutmut.stats import load_stats
from mutmut.stats import status_by_exit_code
from mutmut.ui.helpers import compute_funcs_with_invalid_deps
from mutmut.ui.helpers import find_invalid_dependencies
from mutmut.ui.helpers import get_cache_status
from mutmut.ui.helpers import get_ordered_upstream_and_downstream_functions
from mutmut.utils.file_utils import walk_mutatable_files
from mutmut.utils.format_utils import mangled_name_from_mutant_name
from mutmut.utils.format_utils import raw_func_name_from_mangled


def _run_browser_app(app: Any) -> None:  # pragma: no cover - trivial passthrough, overridden in tests
    """Run the Textual app. Split out so tests can drive it headless."""
    app.run()


def run_result_browser(
    *,
    show_killed: bool,
    get_diff_for_mutant: Callable[..., str],
    apply_mutant: Callable[[str], None],
) -> None:
    """Run the interactive result browser.

    Creates and runs the ResultBrowser Textual app. The ``get_diff_for_mutant`` and
    ``apply_mutant`` callables are injected to avoid a circular import back into
    ``mutmut.__main__``.
    """

    from rich.console import RenderableType
    from rich.syntax import Syntax
    from textual import work
    from textual.app import App
    from textual.containers import Container
    from textual.widget import Widget
    from textual.widgets import DataTable
    from textual.widgets import Footer
    from textual.widgets import Static
    from textual.worker import get_current_worker

    class ResultBrowser(App[None]):
        CSS_PATH = "result_browser_layout.tcss"
        BINDINGS = [
            ("q", "quit()", "Quit"),
            ("r", "retest_mutant()", "Retest mutant"),
            ("f", "retest_function()", "Retest function"),
            ("d", "retest_dependencies()", "Test invalid deps"),
            ("m", "retest_module()", "Retest module"),
            ("a", "apply_mutant()", "Apply mutant to disk"),
            ("t", "view_tests()", "View tests for mutant"),
            ("v", "toggle_dep_level()", "Toggle dep. level"),
            ("g", "generate()", "Generate mutants"),
        ]

        columns: list[tuple[str, str | Text]] = [  # type: ignore[assignment]
            ("path", "Path"),
            ("cache", Text("Cache", justify="right")),
        ] + [(status, Text(emoji, justify="right")) for status, emoji in emoji_by_status.items()]

        cursor_type = "row"
        deps_available = False
        dep_level_index = 0
        source_file_mutation_data_and_stat_by_path: dict[str, tuple[SourceFileMutationData, Stat]] = {}
        path_by_name: dict[str, Path] = {}
        diff_load_lock = Lock()

        def compose(self) -> Iterable[Any]:
            with Container(classes="container"):
                yield DataTable(id="files")
                with Container(id="mutants_container"):
                    yield DataTable(id="mutants")
            with Container(id="depth_options"):
                with Widget(id="diff_view_widget"):
                    yield Static(id="description")
                    yield Static(id="diff_view")
                yield DataTable(id="dependencies")
            yield Footer()

        def on_mount(self) -> None:
            # noinspection PyTypeChecker
            files_table: DataTable[Any] = self.query_one("#files")  # type: ignore[assignment]
            files_table.cursor_type = "row"
            for key, label in self.columns:
                files_table.add_column(key=key, label=label)

            # noinspection PyTypeChecker
            mutants_table: DataTable[Any] = self.query_one("#mutants")  # type: ignore[assignment]
            mutants_table.cursor_type = "row"
            mutants_table.add_columns("name", "status", "cache")

            configured_depth = config().get_effective_dependency_depth()
            if configured_depth in (-1, 0, 1):
                self._depth_options: list[tuple[int, str]] = [(1, "1-lvl"), (0, "full")]
            else:
                self._depth_options = [(1, "1-lvl"), (configured_depth, f"{configured_depth}-lvl"), (0, "full")]

            # noinspection PyTypeChecker
            deps_table: DataTable[Any] = self.query_one("#dependencies")  # type: ignore[assignment]
            deps_table.show_header = True
            deps_table.show_cursor = False
            deps_table.add_columns("↑ Upstream", "↓ Downstream")

            self.read_data()
            self.populate_files_table()

        def read_data(self) -> None:
            self.source_file_mutation_data_and_stat_by_path = {}
            self.path_by_name = {}
            self.cached_by_path: dict[str, CacheStatus] = {}

            self.deps_available = load_stats()

            # Hash the current source so we can spot functions whose logic changed
            # since the mutants were generated (their cached verdicts are stale).
            fresh_hashes: dict[str, str] = {}
            for p in walk_mutatable_files():
                try:
                    fresh_hashes.update(compute_function_hashes(p.read_text()))
                except (OSError, UnicodeDecodeError):
                    continue

            self.invalid_raw_funcs: set[str] = set()
            self.hash_changed_mutants: set[str] = set()

            for p in walk_mutatable_files():
                source_file_mutation_data = SourceFileMutationData(path=p)
                source_file_mutation_data.load()
                stat = collect_stat(source_file_mutation_data)

                self.source_file_mutation_data_and_stat_by_path[str(p)] = source_file_mutation_data, stat
                for name, exit_code in source_file_mutation_data.exit_code_by_key.items():
                    self.path_by_name[name] = p
                    raw_name = raw_func_name_from_mangled(mangled_name_from_mutant_name(name))

                    if exit_code is None:
                        self.invalid_raw_funcs.add(raw_name)
                    elif fresh_hashes:
                        mangled = mangled_name_from_mutant_name(name)
                        func_name = mangled.rsplit(".", 1)[-1] if "." in mangled else mangled
                        stored_hash = source_file_mutation_data.hash_by_function_name.get(func_name)
                        current_hash = fresh_hashes.get(func_name)
                        if stored_hash and current_hash and stored_hash != current_hash:
                            self.invalid_raw_funcs.add(raw_name)
                            self.hash_changed_mutants.add(name)

            if self.deps_available:
                self.funcs_with_invalid_deps = compute_funcs_with_invalid_deps(
                    self.invalid_raw_funcs, state().function_dependencies
                )
                self._raw_deps: dict[str, set[str]] = {}
                for callee, callers in state().function_dependencies.items():
                    raw_callee = raw_func_name_from_mangled(callee)
                    self._raw_deps.setdefault(raw_callee, set())
                    for caller in callers:
                        self._raw_deps[raw_callee].add(raw_func_name_from_mangled(caller))
            else:
                self.funcs_with_invalid_deps = set()
                self._raw_deps = {}

            self._deps_cache: dict[tuple[str, int], tuple[list[tuple[str, int]], list[tuple[str, int]]]] = {}

            for path_str, (source_file_mutation_data, _) in self.source_file_mutation_data_and_stat_by_path.items():
                worst = CacheStatus.CACHED
                for name, exit_code in source_file_mutation_data.exit_code_by_key.items():
                    effective_exit_code = None if name in self.hash_changed_mutants else exit_code
                    worst = worst.worst(get_cache_status(name, effective_exit_code, self.funcs_with_invalid_deps))
                    if worst == CacheStatus.INVALID:
                        break
                self.cached_by_path[path_str] = worst

        def populate_files_table(self) -> None:
            # noinspection PyTypeChecker
            files_table: DataTable[Any] = self.query_one("#files")  # type: ignore[assignment]
            # TODO: restore selection
            selected_row = files_table.cursor_row
            files_table.clear()

            for p, (source_file_mutation_data, stat) in sorted(self.source_file_mutation_data_and_stat_by_path.items()):
                cached_status = self.cached_by_path.get(p, CacheStatus.CACHED)
                row = (
                    [p]
                    + [CACHE_STATUS_EMOJI[cached_status]]
                    + [Text(str(getattr(stat, k.replace(" ", "_"))), justify="right") for k, _ in self.columns[2:]]
                )
                files_table.add_row(*row, key=str(p))

            files_table.move_cursor(row=selected_row)

        def _mutant_row_visible(self, status: str, validity: CacheStatus) -> bool:
            return status not in ("killed", "caught by type check") or show_killed or validity != CacheStatus.CACHED

        def _populate_mutants_table(self, source_file_mutation_data: SourceFileMutationData) -> None:
            # noinspection PyTypeChecker
            mutants_table: DataTable[Any] = self.query_one("#mutants")  # type: ignore[assignment]
            mutants_table.clear()
            for k, v in source_file_mutation_data.exit_code_by_key.items():
                status = status_by_exit_code[v]
                effective_exit_code = None if k in self.hash_changed_mutants else v
                validity = get_cache_status(k, effective_exit_code, self.funcs_with_invalid_deps)
                if self._mutant_row_visible(status, validity):
                    mutants_table.add_row(k, emoji_by_status[status], CACHE_STATUS_EMOJI[validity], key=k)

        def on_data_table_row_highlighted(self, event: Any) -> None:
            if not event.row_key or not event.row_key.value:
                return
            if event.data_table.id == "files":
                source_file_mutation_data, stat = self.source_file_mutation_data_and_stat_by_path[event.row_key.value]
                self._populate_mutants_table(source_file_mutation_data)
            else:
                assert event.data_table.id == "mutants"
                # noinspection PyTypeChecker
                description_view: Static = self.query_one("#description")  # type: ignore[assignment]
                mutant_name = event.row_key.value
                path = self.path_by_name.get(mutant_name)
                source_file_mutation_data, stat = self.source_file_mutation_data_and_stat_by_path[str(path)]

                exit_code = source_file_mutation_data.exit_code_by_key[mutant_name]
                status = status_by_exit_code[exit_code]
                estimated_duration = source_file_mutation_data.estimated_time_of_tests_by_mutant.get(mutant_name, "?")
                duration = source_file_mutation_data.durations_by_key.get(mutant_name, "?")
                type_check_error = source_file_mutation_data.type_check_error_by_key.get(mutant_name, "?")

                view_tests_description = "(press t to view tests executed for this mutant)"

                match status:
                    case "killed":
                        description = f"Killed ({exit_code=}): Mutant caused a test to fail 🎉"
                    case "survived":
                        description = f"Survived ({exit_code=}): No test detected this mutant. {view_tests_description}"
                    case "skipped":
                        description = f"Skipped ({exit_code=})"
                    case "check was interrupted by user":
                        description = f"User interrupted ({exit_code=})"
                    case "caught by type check":
                        description = f"Caught by type checker ({exit_code=}): {type_check_error}"
                    case "timeout":
                        description = (
                            f"Timeout ({exit_code=}): Timed out because tests did not finish within {duration:.3f} seconds. "
                            f"Tests without mutation took {estimated_duration:.3f} seconds. {view_tests_description}"
                        )
                    case "no tests":
                        description = (
                            f"Untested ({exit_code=}): Skipped because selected tests do not execute this code."
                        )
                    case "segfault":
                        description = f"Segfault ({exit_code=}): Running pytest with this mutant segfaulted."
                    case "suspicious":
                        description = (
                            f"Unknown ({exit_code=}): Running pytest with this mutant resulted in an unknown exit code."
                        )
                    case "not checked":
                        description = "Not checked in the last mutmut run."
                    case _:
                        description = f"Unknown status ({exit_code=}, {status=})"
                description_view.update(f"\n {description}\n")

                self._update_dependencies_display(mutant_name)

                diff_view: Static = self.query_one("#diff_view")  # type: ignore[assignment]
                diff_view.update("<loading code diff...>")

                self.load_diff(mutant_name, path, diff_view)

        @work(exclusive=True, thread=True, group="load_diff")
        def load_diff(self, mutant_name: str, path: Path | None, diff_view: Static) -> None:
            """Load the diff for a mutant and display it.

            Only one diff is loaded at a time, and moving on to another mutant cancels the loads
            that have not started yet. Otherwise moving through a long list of mutants piles up
            loads for diffs that are never going to be displayed."""
            worker = get_current_worker()

            with self.diff_load_lock:
                if worker.is_cancelled:
                    return

                try:
                    update: RenderableType = Syntax(get_diff_for_mutant(mutant_name, path=path), "diff")
                except Exception as e:
                    update = f"<{type(e)} {e}>"

            if worker.is_cancelled:
                return

            self.call_from_thread(diff_view.update, update)

        def _update_dependencies_display(self, mutant_name: str) -> None:
            """Refresh the two-column upstream/downstream dependencies table."""
            # noinspection PyTypeChecker
            deps_table: DataTable[Any] = self.query_one("#dependencies")  # type: ignore[assignment]
            deps_table.clear()

            if not self.deps_available:
                return

            raw_func_name = raw_func_name_from_mangled(mangled_name_from_mutant_name(mutant_name))
            max_depth, _ = self._depth_options[self.dep_level_index]

            cache_key = (raw_func_name, max_depth)
            if cache_key in self._deps_cache:
                upstreams, downstreams = self._deps_cache[cache_key]
            else:
                upstreams, downstreams = get_ordered_upstream_and_downstream_functions(
                    raw_func_name, self._raw_deps, max_depth=max_depth
                )
                self._deps_cache[cache_key] = (upstreams, downstreams)

            for i in range(max(len(upstreams), len(downstreams))):
                up_name, up_depth = upstreams[i] if i < len(upstreams) else ("", "")
                down_name, down_depth = downstreams[i] if i < len(downstreams) else ("", "")
                deps_table.add_row(f"{up_depth} {up_name}".strip(), f"{down_depth} {down_name}".strip())

        def action_toggle_dep_level(self) -> None:
            self.dep_level_index = (self.dep_level_index + 1) % len(self._depth_options)
            _, mode_label = self._depth_options[self.dep_level_index]
            self.notify(f"Dependency depth: {mode_label}", severity="information")
            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name is not None:
                self._update_dependencies_display(mutant_name)

        def retest(self, pattern: str | None) -> None:
            if pattern is None:
                return
            self._run_subprocess_command("run", [pattern])

        def view_tests(self, mutant_name: str | None) -> None:
            if mutant_name is None:
                return
            self._run_subprocess_command("tests-for-mutant", [mutant_name])

        def _run_subprocess_command(self, command: str, args: list[str]) -> None:
            with self.suspend():
                browse_index = sys.argv.index("browse")
                initial_args = sys.argv[:browse_index]
                subprocess_args = [sys.executable, *initial_args, command, *args]
                print(">", *subprocess_args)
                subprocess.run(subprocess_args)
                input("press enter to return to browser")

            self.read_data()
            self.populate_files_table()

        def get_mutant_name_from_selection(self) -> str | None:
            # noinspection PyTypeChecker
            mutants_table: DataTable[Any] = self.query_one("#mutants")  # type: ignore[assignment]
            if mutants_table.cursor_row is None or not mutants_table.is_valid_row_index(mutants_table.cursor_row):
                return None

            result: str = mutants_table.get_row_at(mutants_table.cursor_row)[0]
            return result

        def action_retest_mutant(self) -> None:
            self.retest(self.get_mutant_name_from_selection())

        def action_retest_function(self) -> None:
            name = self.get_mutant_name_from_selection()
            if name is not None:
                self.retest(name.rpartition("__mutmut_")[0] + "__mutmut_*")

        def action_retest_module(self) -> None:
            name = self.get_mutant_name_from_selection()
            if name is not None:
                self.retest(name.rpartition(".")[0] + ".*")

        def action_retest_dependencies(self) -> None:
            """Retest the invalid functions the selected mutant transitively depends on."""
            if not self.deps_available:
                self.notify(
                    "Dependency tracking not available. Run mutmut with track_dependencies=true first.",
                    severity="warning",
                )
                return

            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name is None:
                return

            raw_func_name = raw_func_name_from_mangled(mangled_name_from_mutant_name(mutant_name))
            invalid_deps = find_invalid_dependencies(
                raw_func_name, self.invalid_raw_funcs, state().function_dependencies
            )

            if not invalid_deps:
                self.notify("No invalid dependencies found for this function.", severity="information")
                return

            patterns = []
            for dep in invalid_deps:
                module_part, _, func_part = dep.rpartition(".")
                patterns.append(f"{module_part}.x_{func_part}__mutmut_*" if module_part else f"x_{func_part}__mutmut_*")

            self.notify(f"Testing {len(invalid_deps)} invalid dependencies...", severity="information")
            self._run_subprocess_command("run", patterns)

        def action_apply_mutant(self) -> None:
            # noinspection PyTypeChecker
            mutants_table: DataTable[Any] = self.query_one("#mutants")  # type: ignore[assignment]
            if mutants_table.cursor_row is None or not mutants_table.is_valid_row_index(mutants_table.cursor_row):
                return
            apply_mutant(mutants_table.get_row_at(mutants_table.cursor_row)[0])

        def action_view_tests(self) -> None:
            name = self.get_mutant_name_from_selection()
            if name is not None:
                self.view_tests(name)

        def action_generate(self) -> None:
            """Regenerate mutants and refresh hashes without running any tests."""
            self._run_subprocess_command("generate", ["--no-invalidate-callers"])

    _run_browser_app(ResultBrowser())
