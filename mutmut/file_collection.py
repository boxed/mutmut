#!/usr/bin/python
# -*- coding: utf-8 -*-

"""functionality for obtaining both source and test file paths for mutation
testing"""

import os
from os.path import isdir

DEFAULT_TESTS_DIR = 'tests/:test/'


def guess_paths_to_mutate() -> str:
    """guess the path of the source code to mutate"""
    # Guess path with code
    this_dir = os.getcwd().split(os.sep)[-1]
    if isdir('lib'):
        return 'lib'
    elif isdir('src'):
        return 'src'
    elif isdir(this_dir):
        return this_dir
    else:
        raise FileNotFoundError('Could not find code to mutate')


def read_coverage_data(use_coverage):
    """Read a coverage report a ``.coverage`` and return its coverage data.

    :param use_coverage:
    :type use_coverage: bool

    :return:
    :rtype: CoverageData or None
    """
    if use_coverage:
        print('Using coverage data from .coverage file')
        # noinspection PyPackageRequirements,PyUnresolvedReferences
        import coverage
        coverage_data = coverage.CoverageData()
        coverage_data.read_file('.coverage')
        return coverage_data
    else:
        return None


def get_python_source_files(path, tests_dirs):
    """

    :param path:
    :type path: str

    :param tests_dirs:
    :type tests_dirs: list[str]

    :return:
    :rtype:
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
