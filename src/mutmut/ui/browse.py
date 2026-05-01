"""
Result browser UI for mutmut.

This module contains the ResultBrowser Textual application for interactively
browsing mutation test results.
"""

import subprocess
import sys
from collections.abc import Callable
from collections.abc import Generator
from threading import Thread
from typing import Any
from typing import cast

from rich.syntax import Syntax
from rich.text import Text
from textual.app import App
from textual.containers import Container
from textual.widget import Widget
from textual.widgets import DataTable
from textual.widgets import Footer
from textual.widgets import Static

from mutmut.configuration import config
from mutmut.models.cache_status import CACHE_STATUS_EMOJI
from mutmut.models.cache_status import CacheStatus
from mutmut.models.mutant_status import MutantStatus
from mutmut.models.source_file_mutation_data import SourceFileMutationData
from mutmut.mutation.file_mutation import compute_function_hashes
from mutmut.state import state
from mutmut.stats import collect_stat
from mutmut.stats import load_stats
from mutmut.ui.helpers import compute_funcs_with_invalid_deps
from mutmut.ui.helpers import find_invalid_dependencies
from mutmut.ui.helpers import get_cache_status
from mutmut.ui.helpers import get_ordered_upstream_and_downstream_functions
from mutmut.utils.file_utils import walk_mutatable_files
from mutmut.utils.format_utils import mangled_name_from_mutant_name
from mutmut.utils.format_utils import raw_func_name_from_mangled


def run_result_browser(
    *,
    show_killed: bool,
    get_diff_for_mutant: Callable[..., str],
    apply_mutant: Callable[[str], None],
) -> None:
    """Run the interactive result browser.

    This function creates and runs the ResultBrowser Textual app.
    All dependencies are injected to avoid circular imports.

    Args:
        show_killed: Whether to show killed mutants in the list.
        get_diff_for_mutant: Function to get the diff for a mutant.
        apply_mutant: Function to apply a mutant to disk.
    """

    class ResultBrowser(App[None]):
        loading_id = None
        deps_available = False
        dep_level_index = 0
        CSS_PATH = "result_browser_layout.tcss"
        BINDINGS = [
            ("q", "quit()", "Quit"),
            ("r", "retest_mutant()", "Test mutant"),
            ("f", "retest_function()", "Test function"),
            ("d", "retest_dependencies()", "Test invalid deps"),
            ("m", "retest_module()", "Test module"),
            ("a", "apply_mutant()", "Apply mutant to disk"),
            ("t", "view_tests()", "View tests for mutant"),
            ("v", "toggle_dep_level()", "Toggle dep. level"),
            ("g", "generate()", "Generate mutants"),
        ]

        columns: list[tuple[str, str | Text]] = [  # type: ignore[assignment]
            ("path", "Path"),
            ("cache", Text("Cache", justify="right")),
        ] + [(s.text, Text(s.emoji, justify="right")) for s in MutantStatus]

        cursor_type = "row"
        source_file_mutation_data_and_stat_by_path: dict[str, tuple[SourceFileMutationData, object]] = {}

        def compose(self) -> Generator[Widget, None, None]:
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
            files_table: DataTable[Text | str] = self.query_one("#files")  # type: ignore[assignment]
            files_table.cursor_type = "row"
            for key, label in self.columns:
                files_table.add_column(key=key, label=label)

            # noinspection PyTypeChecker
            mutants_table: DataTable[str] = self.query_one("#mutants")  # type: ignore[assignment]
            mutants_table.cursor_type = "row"
            mutants_table.add_columns("name", "status", "cache")

            configured_depth = config().get_effective_dependency_depth()
            if configured_depth == -1 or configured_depth == 0:
                self._depth_options: list[tuple[int, str]] = [(1, "1-lvl"), (0, "full")]
            elif configured_depth == 1:
                self._depth_options = [(1, "1-lvl"), (0, "full")]
            else:
                self._depth_options = [(1, "1-lvl"), (configured_depth, f"{configured_depth}-lvl"), (0, "full")]

            deps_table: DataTable[str] = cast(DataTable[str], self.query_one("#dependencies"))
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

            fresh_hashes: dict[str, str] = {}
            for p in walk_mutatable_files():
                try:
                    source_code = p.read_text()
                    file_hashes = compute_function_hashes(source_code)
                    fresh_hashes.update(file_hashes)
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
                    if raw_callee not in self._raw_deps:
                        self._raw_deps[raw_callee] = set()
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
                    cache_status = get_cache_status(name, effective_exit_code, self.funcs_with_invalid_deps)
                    worst = worst.worst(cache_status)
                    if worst == CacheStatus.INVALID:
                        break
                self.cached_by_path[path_str] = worst

        def populate_files_table(self) -> None:
            # noinspection PyTypeChecker
            files_table: DataTable[Any] = cast(DataTable[Any], self.query_one("#files"))
            selected_row = files_table.cursor_row
            files_table.clear()

            for p, (_, stat) in sorted(self.source_file_mutation_data_and_stat_by_path.items()):
                cached_status = self.cached_by_path.get(p, CacheStatus.CACHED)
                row = (
                    [p]
                    + [CACHE_STATUS_EMOJI[cached_status]]
                    + [Text(str(getattr(stat, k.replace(" ", "_"))), justify="right") for k, _ in self.columns[2:]]
                )
                files_table.add_row(*row, key=str(p))

            files_table.move_cursor(row=selected_row)

            self._refresh_mutants_table()

        def _refresh_mutants_table(self) -> None:
            """Refresh the mutants table for the currently selected file."""
            files_table: DataTable[Any] = cast(DataTable[Any], self.query_one("#files"))
            if files_table.cursor_row is None:
                return

            try:
                row_key = files_table.get_row_at(files_table.cursor_row)
                if not row_key:
                    return
                path = row_key[0]
            except Exception:
                return

            source_file_mutation_data, _ = self.source_file_mutation_data_and_stat_by_path.get(str(path), (None, None))
            if not source_file_mutation_data:
                return

            mutants_table: DataTable[Any] = cast(DataTable[Any], self.query_one("#mutants"))
            mutants_table.clear()
            for k, v in source_file_mutation_data.exit_code_by_key.items():
                status = MutantStatus.from_exit_code(v)
                effective_exit_code = None if k in self.hash_changed_mutants else v
                validity = get_cache_status(k, effective_exit_code, self.funcs_with_invalid_deps)
                if (
                    status not in (MutantStatus.KILLED, MutantStatus.TYPECHECK)
                    or show_killed
                    or validity != CacheStatus.CACHED
                ):
                    mutants_table.add_row(k, status.emoji, CACHE_STATUS_EMOJI[validity], key=k)

        def on_data_table_row_highlighted(self, event: Any) -> None:
            if not event.row_key or not event.row_key.value:
                return
            if event.data_table.id == "files":
                # noinspection PyTypeChecker
                mutants_table: DataTable[Any] = cast(DataTable[Any], self.query_one("#mutants"))
                mutants_table.clear()
                source_file_mutation_data, _ = self.source_file_mutation_data_and_stat_by_path[event.row_key.value]
                for k, v in source_file_mutation_data.exit_code_by_key.items():
                    status = MutantStatus.from_exit_code(v)
                    effective_exit_code = None if k in self.hash_changed_mutants else v
                    validity = get_cache_status(k, effective_exit_code, self.funcs_with_invalid_deps)
                    if (
                        status not in (MutantStatus.KILLED, MutantStatus.TYPECHECK)
                        or show_killed
                        or validity != CacheStatus.CACHED
                    ):
                        mutants_table.add_row(k, status.emoji, CACHE_STATUS_EMOJI[validity], key=k)
            else:
                assert event.data_table.id == "mutants"
                # noinspection PyTypeChecker
                description_view = cast(Static, self.query_one("#description"))
                mutant_name = event.row_key.value
                self.loading_id = mutant_name
                path = self.path_by_name.get(mutant_name)
                source_file_mutation_data, stat = self.source_file_mutation_data_and_stat_by_path[str(path)]

                exit_code = source_file_mutation_data.exit_code_by_key[mutant_name]
                status = MutantStatus.from_exit_code(exit_code)
                estimated_duration = source_file_mutation_data.estimated_time_of_tests_by_mutant.get(mutant_name, "?")
                duration = source_file_mutation_data.durations_by_key.get(mutant_name, "?")
                type_check_error = source_file_mutation_data.type_check_error_by_key.get(mutant_name, "?")

                view_tests_description = "(press t to view tests executed for this mutant)"

                match status:
                    case MutantStatus.KILLED:
                        description = f"Killed ({exit_code=}): Mutant caused a test to fail 🎉"
                    case MutantStatus.SURVIVED:
                        description = f"Survived ({exit_code=}): No test detected this mutant. {view_tests_description}"
                    case MutantStatus.SKIPPED:
                        description = f"Skipped ({exit_code=})"
                    case MutantStatus.CHECK_INTERRUPTED_BY_USER:
                        description = f"User interrupted ({exit_code=})"
                    case MutantStatus.TYPECHECK:
                        description = f"Caught by type checker ({exit_code=}): {type_check_error}"
                    case MutantStatus.TIMEOUT:
                        description = (
                            f"Timeout ({exit_code=}): Timed out because tests did not finish within {duration:.3f} seconds. "
                            f"Tests without mutation took {estimated_duration:.3f} seconds. {view_tests_description}"
                        )
                    case MutantStatus.NO_TESTS:
                        description = (
                            f"Untested ({exit_code=}): Skipped because selected tests do not execute this code."
                        )
                    case MutantStatus.SEGFAULT:
                        description = f"Segfault ({exit_code=}): Running pytest with this mutant segfaulted."
                    case MutantStatus.SUSPICIOUS:
                        description = (
                            f"Unknown ({exit_code=}): Running pytest with this mutant resulted in an unknown exit code."
                        )
                    case MutantStatus.NOT_CHECKED:
                        description = "Not checked in the last mutmut run."
                    case _:
                        description = f"Unknown status ({exit_code=}, {status=})"
                description_view.update(f"\n {description}\n")

                self._update_dependencies_display(mutant_name)

                diff_view = cast(Static, self.query_one("#diff_view"))
                diff_view.update("<loading code diff...>")

                def load_thread() -> None:
                    try:
                        d = get_diff_for_mutant(event.row_key.value, path=path)
                        if event.row_key.value == self.loading_id:
                            diff_view.update(Syntax(d, "diff"))
                    except Exception as e:
                        diff_view.update(f"<{type(e)} {e}>")

                t = Thread(target=load_thread)
                t.start()

        def retest(self, pattern: str) -> None:
            self._run_subprocess_command("run", [pattern])

        def view_tests(self, mutant_name: str) -> None:
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
            mutants_table: DataTable[Any] = cast(DataTable[Any], self.query_one("#mutants"))
            if mutants_table.cursor_row is None or not mutants_table.is_valid_row_index(mutants_table.cursor_row):
                return None

            return str(mutants_table.get_row_at(mutants_table.cursor_row)[0])

        def action_retest_mutant(self) -> None:
            name = self.get_mutant_name_from_selection()
            if name:
                self.retest(name)

        def action_retest_function(self) -> None:
            name = self.get_mutant_name_from_selection()
            if name:
                self.retest(name.rpartition("__mutmut_")[0] + "__mutmut_*")

        def action_retest_module(self) -> None:
            name = self.get_mutant_name_from_selection()
            if name:
                self.retest(name.rpartition(".")[0] + ".*")

        def action_retest_dependencies(self) -> None:
            """Test invalid dependencies (callees) of the selected function."""
            if not self.deps_available:
                self.notify(
                    "Dependency tracking not available. Run mutmut with track_dependencies=true first.",
                    severity="warning",
                )
                return

            mutant_name = self.get_mutant_name_from_selection()
            if not mutant_name:
                return

            mangled = mangled_name_from_mutant_name(mutant_name)
            raw_func_name = raw_func_name_from_mangled(mangled)

            invalid_deps = find_invalid_dependencies(
                raw_func_name, self.invalid_raw_funcs, state().function_dependencies
            )

            if not invalid_deps:
                self.notify("No invalid dependencies found for this function.", severity="information")
                return

            patterns = []
            for dep in invalid_deps:
                module_part, _, func_part = dep.rpartition(".")
                mangled_pattern = (
                    f"{module_part}.x_{func_part}__mutmut_*" if module_part else f"x_{func_part}__mutmut_*"
                )
                patterns.append(mangled_pattern)

            self.notify(f"Testing {len(invalid_deps)} invalid dependencies...", severity="information")
            self._run_subprocess_command("run", patterns)

        def _update_dependencies_display(self, mutant_name: str) -> None:
            """Update the dependencies display for a mutant."""
            deps_table: DataTable[Any] = cast(DataTable[Any], self.query_one("#dependencies"))
            deps_table.clear()

            if not self.deps_available:
                return

            mangled = mangled_name_from_mutant_name(mutant_name)
            raw_func_name = raw_func_name_from_mangled(mangled)

            max_depth, _ = self._depth_options[self.dep_level_index]

            cache_key = (raw_func_name, max_depth)
            if cache_key in self._deps_cache:
                upstreams, downstreams = self._deps_cache[cache_key]
            else:
                upstreams, downstreams = get_ordered_upstream_and_downstream_functions(
                    raw_func_name, self._raw_deps, max_depth=max_depth
                )
                self._deps_cache[cache_key] = (upstreams, downstreams)

            max_rows = max(len(upstreams), len(downstreams))

            for i in range(max_rows):
                upstream = upstreams[i] if i < len(upstreams) else ("", "")
                upstream_text = f"{upstream[1]} {upstream[0]}"

                downstream = downstreams[i] if i < len(downstreams) else ("", "")
                downstream_text = f"{downstream[1]} {downstream[0]}"
                deps_table.add_row(upstream_text, downstream_text)

        def action_toggle_dep_level(self) -> None:
            """Cycle through dependency depth options."""
            self.dep_level_index = (self.dep_level_index + 1) % len(self._depth_options)
            _, mode_label = self._depth_options[self.dep_level_index]
            self.notify(f"Dependency depth: {mode_label}", severity="information")
            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name:
                self._update_dependencies_display(mutant_name)

        def action_apply_mutant(self) -> None:
            # noinspection PyTypeChecker
            mutants_table: DataTable[Any] = cast(DataTable[Any], self.query_one("#mutants"))
            if mutants_table.cursor_row is None or not mutants_table.is_valid_row_index(mutants_table.cursor_row):
                return
            apply_mutant(str(mutants_table.get_row_at(mutants_table.cursor_row)[0]))

        def action_view_tests(self) -> None:
            name = self.get_mutant_name_from_selection()
            if name:
                self.view_tests(name)

        def action_generate(self) -> None:
            """Generate mutants and update hashes without running tests."""
            self._run_subprocess_command("generate", ["--no-invalidate-callers"])

    ResultBrowser().run()
