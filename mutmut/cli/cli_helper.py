#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from typing import List

import click

from mutmut import (
    mutate_file,
    Context,
    add_mutations_by_file,
    python_source_files,
)
from mutmut.cache import filename_and_mutation_id_from_pk, update_line_numbers


def do_apply(mutation_pk: str, dict_synonyms: List[str], backup: bool):
    """Apply a specified mutant to the source code

    :param mutation_pk: mutmut cache primary key of the mutant to apply
    :param dict_synonyms: list of synonym keywords for a python dictionary
    :param backup: if :obj:`True` create a backup of the source file
        before applying the mutation
    """
    filename, mutation_id = filename_and_mutation_id_from_pk(int(mutation_pk))

    update_line_numbers(filename)

    context = Context(
        mutation_id=mutation_id,
        filename=filename,
        dict_synonyms=dict_synonyms,
    )
    mutate_file(
        backup=backup,
        context=context,
    )


"""
CodeScene analysis:
    This function is recommended to be refactored because of:
        - Complex method: cyclomatic complexity equal to 10, with threshold equal to 9
        - Excess number of function arguments: 7 arguments, with threshold equal to 4
        - Bumpy Road Ahead: 2 blocks with nested conditional logic, any nesting of 2 or deeper is considered, 
            with threshold equal to one single nested block per function
        - Deep, Nested Complexity: a nested complexity depth of 4, with threshold equal to 4
"""


def parse_run_argument(argument, config, dict_synonyms, mutations_by_file, paths_to_exclude, paths_to_mutate,
                       tests_dirs):
    if argument is None:
        iterate_over_paths_to_mutate(paths_to_mutate, tests_dirs, paths_to_exclude, dict_synonyms, config,
                                     mutations_by_file)
        return

    # Try to convert the argument to an integer
    try:
        # Convert the argument to an integer
        int(argument)

    # If the argument cannot be converted to an integer, then the argument is a filename
    except ValueError:

        # If the filename does not exist, then raise a BadArgumentUsage exception
        filename = argument
        check_file_exists(filename)

        # Update the line numbers in the filename
        update_line_numbers(filename)

        # Add the mutations by file
        add_mutations_by_file(mutations_by_file, filename, dict_synonyms, config)
        return

    filename, mutation_id = filename_and_mutation_id_from_pk(int(argument))
    update_line_numbers(filename)
    mutations_by_file[filename] = [mutation_id]


def iterate_over_paths_to_mutate(paths_to_mutate, tests_dirs, paths_to_exclude, dict_synonyms, config,
                                 mutations_by_file):
    for path in paths_to_mutate:
        iterate_over_python_source_files(path, tests_dirs, paths_to_exclude, mutations_by_file, dict_synonyms, config)


def iterate_over_python_source_files(path, tests_dirs, paths_to_exclude, mutations_by_file, dict_synonyms, config):
    for filename in python_source_files(path, tests_dirs, paths_to_exclude):
        update_lines_and_mutations_by_file(mutations_by_file, filename, dict_synonyms, config)


def update_lines_and_mutations_by_file(mutations_by_file, filename, dict_synonyms, config):
    if filename.startswith('test_') or filename.endswith('__tests.py'):
        return

    update_line_numbers(filename)
    add_mutations_by_file(mutations_by_file, filename, dict_synonyms, config)


def check_file_exists(filename):
    if not os.path.exists(filename):
        raise click.BadArgumentUsage(f'File {filename} does not exist')
