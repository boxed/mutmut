"""
Result browser UI for mutmut.

This module contains the ResultBrowser Textual application for interactively
browsing mutation test results.
"""

import subprocess
import sys
from collections.abc import Callable
from collections.abc import Generator
from pathlib import Path
from threading import Thread

from rich.syntax import Syntax
from rich.text import Text
from textual.app import App
from textual.containers import Container
from textual.widget import Widget
from textual.widgets import DataTable
from textual.widgets import Footer
from textual.widgets import Static

from mutmut.models.source_file_mutation_data import SourceFileMutationData
from mutmut.stats import collect_stat
from mutmut.stats import emoji_by_status
from mutmut.stats import status_by_exit_code
from mutmut.utils.file_utils import walk_mutatable_files


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
        status_by_exit_code: Mapping from exit codes to status strings.
        emoji_by_status: Mapping from status strings to emoji.
        walk_source_files: Generator yielding source file paths.
        collect_stat: Function to collect stats for a mutation data object.
        get_diff_for_mutant: Function to get the diff for a mutant.
        apply_mutant: Function to apply a mutant to disk.
    """

    class ResultBrowser(App[None]):
        loading_id = None
        CSS_PATH = "result_browser_layout.tcss"
        BINDINGS = [
            ("q", "quit()", "Quit"),
            ("r", "retest_mutant()", "Retest mutant"),
            ("f", "retest_function()", "Retest function"),
            ("m", "retest_module()", "Retest module"),
            ("a", "apply_mutant()", "Apply mutant to disk"),
            ("t", "view_tests()", "View tests for mutant"),
        ]

        columns = [
            ("path", "Path"),
        ] + [(status, Text(emoji, justify="right")) for status, emoji in emoji_by_status.items()]

        cursor_type = "row"
        source_file_mutation_data_and_stat_by_path: dict[str, tuple[SourceFileMutationData, object]] = {}

        def compose(self) -> Generator[Widget, None, None]:
            with Container(classes="container"):
                yield DataTable(id="files")
                yield DataTable(id="mutants")
            with Widget(id="diff_view_widget"):
                yield Static(id="description")
                yield Static(id="diff_view")
            yield Footer()

        def on_mount(self) -> None:
            # files table
            # noinspection PyTypeChecker
            files_table: DataTable[Text | str] = self.query_one("#files")  # type: ignore[assignment]
            files_table.cursor_type = "row"
            for key, label in self.columns:
                files_table.add_column(key=key, label=label)

            # mutants table
            # noinspection PyTypeChecker
            mutants_table: DataTable[str] = self.query_one("#mutants")  # type: ignore[assignment]
            mutants_table.cursor_type = "row"
            mutants_table.add_columns("name", "status")

            self.read_data()
            self.populate_files_table()

        def read_data(self) -> None:
            self.source_file_mutation_data_and_stat_by_path = {}
            self.path_by_name: dict[str, Path] = {}

            for p in walk_mutatable_files():
                source_file_mutation_data = SourceFileMutationData(path=p)
                source_file_mutation_data.load()
                stat = collect_stat(source_file_mutation_data)

                self.source_file_mutation_data_and_stat_by_path[str(p)] = source_file_mutation_data, stat
                for name in source_file_mutation_data.exit_code_by_key:
                    self.path_by_name[name] = p

        def populate_files_table(self) -> None:
            # noinspection PyTypeChecker
            files_table: DataTable[Text | str] = self.query_one("#files")  # type: ignore[assignment]
            # TODO: restore selection
            selected_row = files_table.cursor_row
            files_table.clear()

            for p, (_source_file_mutation_data, stat) in sorted(
                self.source_file_mutation_data_and_stat_by_path.items()
            ):
                row = [p] + [
                    Text(str(getattr(stat, k.replace(" ", "_"))), justify="right") for k, _ in self.columns[1:]
                ]
                files_table.add_row(*row, key=str(p))

            files_table.move_cursor(row=selected_row)

        def on_data_table_row_highlighted(self, event: object) -> None:
            if not event.row_key or not event.row_key.value:  # type: ignore[attr-defined]
                return
            if event.data_table.id == "files":  # type: ignore[attr-defined]
                # noinspection PyTypeChecker
                mutants_table: DataTable[str] = self.query_one("#mutants")  # type: ignore[assignment]
                mutants_table.clear()
                source_file_mutation_data, stat = self.source_file_mutation_data_and_stat_by_path[event.row_key.value]  # type: ignore[attr-defined]
                for k, v in source_file_mutation_data.exit_code_by_key.items():
                    status = status_by_exit_code[v]
                    if status not in ("killed", "caught by type check") or show_killed:
                        mutants_table.add_row(k, emoji_by_status[status], key=k)
            else:
                assert event.data_table.id == "mutants"  # type: ignore[attr-defined]
                # noinspection PyTypeChecker
                description_view: Static = self.query_one("#description")  # type: ignore[assignment]
                mutant_name = event.row_key.value  # type: ignore[attr-defined]
                self.loading_id = mutant_name
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

                diff_view: Static = self.query_one("#diff_view")  # type: ignore[assignment]
                diff_view.update("<loading code diff...>")

                def load_thread() -> None:
                    try:
                        d = get_diff_for_mutant(event.row_key.value, path=path)  # type: ignore[attr-defined]
                        if event.row_key.value == self.loading_id:  # type: ignore[attr-defined]
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

        def get_mutant_name_from_selection(self) -> str:
            # noinspection PyTypeChecker
            mutants_table: DataTable[str] = self.query_one("#mutants")  # type: ignore[assignment]
            if mutants_table.cursor_row is None or not mutants_table.is_valid_row_index(mutants_table.cursor_row):
                return ""

            return mutants_table.get_row_at(mutants_table.cursor_row)[0]

        def action_retest_mutant(self) -> None:
            self.retest(self.get_mutant_name_from_selection())

        def action_retest_function(self) -> None:
            self.retest(self.get_mutant_name_from_selection().rpartition("__mutmut_")[0] + "__mutmut_*")

        def action_retest_module(self) -> None:
            self.retest(self.get_mutant_name_from_selection().rpartition(".")[0] + ".*")

        def action_apply_mutant(self) -> None:
            # noinspection PyTypeChecker
            mutants_table: DataTable[str] = self.query_one("#mutants")  # type: ignore[assignment]
            if mutants_table.cursor_row is None or not mutants_table.is_valid_row_index(mutants_table.cursor_row):
                return
            apply_mutant(mutants_table.get_row_at(mutants_table.cursor_row)[0])

        def action_view_tests(self) -> None:
            self.view_tests(self.get_mutant_name_from_selection())

    ResultBrowser().run()
