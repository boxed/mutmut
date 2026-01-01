import subprocess  # noqa: S404
import sys
from threading import Thread
from typing import Any, ClassVar, cast

import click
from rich.text import Text

from nootnoot.app.config import ensure_config_loaded, get_config
from nootnoot.app.meta import SourceFileMutationData
from nootnoot.app.mutation import (
    Stat,
    apply_mutant,
    collect_stat,
    emoji_by_status,
    get_diff_for_mutant,
    status_by_exit_code,
    unused,
    walk_source_files,
)
from nootnoot.app.state import NootNootState


@click.command()
@click.option("--show-killed", is_flag=True, default=False, help="Display killed mutants.")
@click.pass_obj
def browse(state: NootNootState, *, show_killed: bool) -> None:
    ensure_config_loaded(state)

    from rich.syntax import Syntax  # noqa: PLC0415
    from textual.app import App  # noqa: PLC0415
    from textual.containers import Container  # noqa: PLC0415
    from textual.widget import Widget  # noqa: PLC0415
    from textual.widgets import DataTable, Footer, Static  # noqa: PLC0415

    class ResultBrowser(App):
        CSS_PATH: ClassVar[str] = "result_browser_layout.tcss"
        BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
            ("q", "quit()", "Quit"),
            ("r", "retest_mutant()", "Retest mutant"),
            ("f", "retest_function()", "Retest function"),
            ("m", "retest_module()", "Retest module"),
            ("a", "apply_mutant()", "Apply mutant to disk"),
            ("t", "view_tests()", "View tests for mutant"),
        ]

        columns: ClassVar[list[tuple[str, Text | str]]] = [
            ("path", "Path"),
        ] + [(status, Text(emoji, justify="right")) for status, emoji in emoji_by_status.items()]

        cursor_type: ClassVar[str] = "row"

        def __init__(self, **kwargs: Any):
            super().__init__(**kwargs)
            self._state = state
            self.loading_id: str | None = None
            self.source_file_mutation_data_and_stat_by_path: dict[
                str, tuple[SourceFileMutationData, Stat]
            ] = {}
            self.path_by_name: dict[str, str] = {}

        def compose(self):
            unused(self)
            with Container(classes="container"):
                yield DataTable(id="files")
                yield DataTable(id="mutants")
            with Widget(id="diff_view_widget"):
                yield Static(id="description")
                yield Static(id="diff_view")
            yield Footer()

        def on_mount(self):
            # files table
            files_table = cast("DataTable", self.query_one("#files"))
            files_table.cursor_type = "row"
            for key, label in self.columns:
                files_table.add_column(key=key, label=label)

            # mutants table
            mutants_table = cast("DataTable", self.query_one("#mutants"))
            mutants_table.cursor_type = "row"
            mutants_table.add_columns("name", "status")

            self.read_data()
            self.populate_files_table()

        def read_data(self):
            config = get_config(self._state)
            self.source_file_mutation_data_and_stat_by_path = {}
            self.path_by_name = {}

            for p in walk_source_files(self._state):
                if config.should_ignore_for_mutation(p):
                    continue
                source_file_mutation_data = SourceFileMutationData(path=p)
                source_file_mutation_data.load(debug=config.debug)
                stat = collect_stat(source_file_mutation_data)

                path_key = str(p)
                self.source_file_mutation_data_and_stat_by_path[path_key] = (
                    source_file_mutation_data,
                    stat,
                )
                for name in source_file_mutation_data.exit_code_by_key:
                    self.path_by_name[name] = path_key

        def populate_files_table(self):
            files_table = cast("DataTable", self.query_one("#files"))
            # TODO: restore selection
            selected_row = files_table.cursor_row
            files_table.clear()

            for p, (_source_file_mutation_data, stat_for_row) in sorted(
                self.source_file_mutation_data_and_stat_by_path.items()
            ):
                row = [p] + [
                    Text(str(getattr(stat_for_row, k.replace(" ", "_"))), justify="right")
                    for k, _ in self.columns[1:]
                ]
                files_table.add_row(*row, key=str(p))

            files_table.move_cursor(row=selected_row)

        def on_data_table_row_highlighted(self, event):  # noqa: PLR0912, PLR0915
            if not event.row_key or not event.row_key.value:
                return
            if event.data_table.id == "files":
                mutants_table = cast("DataTable", self.query_one("#mutants"))
                mutants_table.clear()
                source_file_mutation_data, _stat = self.source_file_mutation_data_and_stat_by_path[
                    event.row_key.value
                ]
                for k, v in source_file_mutation_data.exit_code_by_key.items():
                    status = status_by_exit_code[v]
                    if status != "killed" or show_killed:
                        mutants_table.add_row(k, emoji_by_status[status], key=k)
            else:
                if event.data_table.id != "mutants":
                    msg = f"Unexpected data table {event.data_table.id}"
                    raise ValueError(msg)
                description_view = cast("Static", self.query_one("#description"))
                mutant_name = event.row_key.value
                self.loading_id = mutant_name
                path = self.path_by_name.get(mutant_name)
                if path is None:
                    msg = f"Path for mutant {mutant_name} is unknown"
                    raise ValueError(msg)
                source_file_mutation_data, _stat = self.source_file_mutation_data_and_stat_by_path[path]

                exit_code = source_file_mutation_data.exit_code_by_key[mutant_name]
                status = status_by_exit_code[exit_code]
                estimated_duration = source_file_mutation_data.estimated_time_of_tests_by_mutant.get(
                    mutant_name, "?"
                )
                duration = source_file_mutation_data.durations_by_key.get(mutant_name, "?")

                view_tests_description = "(press t to view tests executed for this mutant)"

                match status:
                    case "killed":
                        description = f"Killed ({exit_code=}): Mutant caused a test to fail 🎉"
                    case "survived":
                        description = (
                            f"Survived ({exit_code=}): No test detected this mutant. {view_tests_description}"
                        )
                    case "skipped":
                        description = f"Skipped ({exit_code=})"
                    case "check was interrupted by user":
                        description = f"User interrupted ({exit_code=})"
                    case "timeout":
                        description = (
                            f"Timeout ({exit_code=}): Timed out because tests did not finish "
                            f"within {duration:.3f} seconds. Tests without mutation took "
                            f"{estimated_duration:.3f} seconds. {view_tests_description}"
                        )
                    case "no tests":
                        description = (
                            f"Untested ({exit_code=}): Skipped because selected tests do not "
                            "execute this code."
                        )
                    case "segfault":
                        description = f"Segfault ({exit_code=}): Running pytest with this mutant segfaulted."
                    case "suspicious":
                        description = (
                            f"Unknown ({exit_code=}): Running pytest with this mutant resulted "
                            "in an unknown exit code."
                        )
                    case "not checked":
                        description = "Not checked in the last nootnoot run."
                    case _:
                        description = f"Unknown status ({exit_code=}, {status=})"
                description_view.update(f"\n {description}\n")

                diff_view = cast("Static", self.query_one("#diff_view"))
                diff_view.update("<loading code diff...>")

                def load_thread():
                    ensure_config_loaded(self._state)
                    try:
                        d = get_diff_for_mutant(self._state, event.row_key.value, path=path)
                        if event.row_key.value == self.loading_id:
                            diff_view.update(Syntax(d, "diff"))
                    except Exception as e:  # noqa: BLE001
                        diff_view.update(f"<{type(e)} {e}>")

                t = Thread(target=load_thread)
                t.start()

        def retest(self, pattern):
            self._run_subprocess_command("run", [pattern])

        def view_tests(self, mutant_name: str) -> None:
            self._run_subprocess_command("tests-for-mutant", [mutant_name])

        def _run_subprocess_command(self, command: str, args: list[str]) -> None:
            with self.suspend():
                browse_index = sys.argv.index("browse")
                initial_args = sys.argv[:browse_index]
                subprocess_args = [sys.executable, *initial_args, command, *args]
                print(">", *subprocess_args, file=sys.stderr)
                subprocess.run(subprocess_args, check=False)  # noqa: S603
                input("press enter to return to browser")

            self.read_data()
            self.populate_files_table()

        def get_mutant_name_from_selection(self):
            mutants_table = cast("DataTable", self.query_one("#mutants"))
            if mutants_table.cursor_row is None:
                return None

            row = mutants_table.get_row_at(mutants_table.cursor_row)
            return str(row[0])

        def action_retest_mutant(self):
            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name is None:
                return
            self.retest(mutant_name)

        def action_retest_function(self):
            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name is None:
                return
            self.retest(mutant_name.rpartition("__nootnoot_")[0] + "__nootnoot_*")

        def action_retest_module(self):
            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name is None:
                return
            self.retest(mutant_name.rpartition(".")[0] + ".*")

        def action_apply_mutant(self):
            ensure_config_loaded(self._state)
            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name is None:
                return
            apply_mutant(self._state, mutant_name)

        def action_view_tests(self):
            mutant_name = self.get_mutant_name_from_selection()
            if mutant_name is None:
                return
            self.view_tests(mutant_name)

    ResultBrowser().run()
