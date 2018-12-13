#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Functionality for obtaining both source and test files for mutation
testing and generating a dictionary of valid mutations"""

import os
from os.path import isdir


def python_source_files(path, tests_dirs):
    """Yield the paths to all python source files

    :param path: path of the source file to mutate or path of the directory to
        yield source files from to mutate
    :type path: str

    :param tests_dirs: list of the directories containing testing files
    :type tests_dirs: list[str]

    :return: Generator yielding paths to python source files
    """
    if isdir(path):
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if
                       os.path.join(root, d) not in tests_dirs]
            for filename in files:
                if filename.endswith('.py'):
                    yield os.path.join(root, filename)
    else:
        yield path


def get_or_guess_paths_to_mutate():
    """Guess the path of the source code directory to mutate if no specific
    path is given

    :return: The path to source code to mutate
    :rtype: str
    """
    # Guess path with code
    this_dir = os.getcwd().split(os.sep)[-1]
    if isdir('lib'):
        return 'lib'
    elif isdir('src'):
        return 'src'
    elif isdir(this_dir):
        return this_dir
    else:
        raise FileNotFoundError(
            'Could not figure out where the code to mutate is. '
            'Please specify it on the command line like "mutmut code_dir" '
            'or by adding "paths_to_mutate=code_dir" in setup.cfg '
            'under the section [mutmut]'
        )


def read_coverage_data():
    """Read a coverage report a ``.coverage`` and return its coverage data.

    :return: CoverageData from the given coverage file path
    :rtype: CoverageData or None
    """
    print('Using coverage data from .coverage file')
    # noinspection PyPackageRequirements,PyUnresolvedReferences
    import coverage
    coverage_data = coverage.CoverageData()
    coverage_data.read_file('.coverage')
    return coverage_data
