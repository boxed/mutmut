from typing import Dict, List

from mutmut.cache import filename_and_mutation_id_from_pk, update_line_numbers
from mutmut.cli.helper.utils import check_file_exists, python_source_files
from mutmut.mutator.mutator import Mutator
from mutmut.helpers.context import Context
from mutmut.helpers.relativemutationid import RelativeMutationID


class RunArgumentParser:

    def __init__(self, argument, config, dict_synonyms, mutations_by_file, paths_to_exclude, paths_to_mutate,
                 tests_dirs):

        self.argument = argument
        self.config = config
        self.dict_synonyms = dict_synonyms
        self.mutations_by_file = mutations_by_file
        self.paths_to_exclude = paths_to_exclude
        self.paths_to_mutate = paths_to_mutate
        self.tests_dirs = tests_dirs

    def parse_run_argument(self):
        if self.argument is None:
            self.iterate_over_paths_to_mutate()
            return

        try:
            int(self.argument)
        except ValueError:
            filename = self.argument
            check_file_exists(filename)
            update_line_numbers(filename)
            self.add_mutations_by_file(self.mutations_by_file, filename, self.dict_synonyms)
            return

        filename, mutation_id = filename_and_mutation_id_from_pk(int(self.argument))
        update_line_numbers(filename)
        self.mutations_by_file[filename] = [mutation_id]

    def iterate_over_paths_to_mutate(self):
        for path in self.paths_to_mutate:
            self.iterate_over_python_source_files(path)

    def iterate_over_python_source_files(self, path):
        for filename in python_source_files(path, self.tests_dirs, self.paths_to_exclude):
            self.update_lines_and_mutations_by_file(filename)

    def update_lines_and_mutations_by_file(self, filename):
        if filename.startswith('test_') or filename.endswith('__tests.py'):
            return

        update_line_numbers(filename)
        self.add_mutations_by_file(self.mutations_by_file, filename, self.dict_synonyms)

    def add_mutations_by_file(
            self,
            mutations_by_file: Dict[str, List[RelativeMutationID]],
            filename: str,
            dict_synonyms: List[str]
    ):
        with open(filename) as f:
            source = f.read()
        context = Context(
            source=source,
            filename=filename,
            config=self.config,
            dict_synonyms=dict_synonyms,
        )

        try:
            mutator = Mutator(context)
            mutations_by_file[filename] = mutator.list_mutations()
            from mutmut.cache import register_mutants

            register_mutants(mutations_by_file)
        except Exception as e:
            raise RuntimeError(
                'Failed while creating mutations for {}, for line "{}"'.format(
                    context.filename, context.current_source_line
                )
            ) from e

