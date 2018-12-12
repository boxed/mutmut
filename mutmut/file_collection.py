#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Functionality for obtaining both source and test files for mutation
testing and generating a dictionary of valid mutations"""

import os

from glob2 import glob

DEFAULT_TESTS_DIR = 'tests/:test/'


def guess_paths_to_mutate():
    """Guess the path of the source code to mutate

    :return: The path to source code to mutate
    :rtype: str
    """
    # Guess path with code
    this_dir = os.getcwd().split(os.sep)[-1]
    if os.path.isdir('lib'):
        return 'lib'
    elif os.path.isdir('src'):
        return 'src'
    elif os.path.isdir(this_dir):
        return this_dir
    else:
        raise FileNotFoundError('Could not find code to mutate')


def read_coverage_data(coverage_path):
    """Read a coverage report a ``.coverage`` and return its coverage data.

    :param coverage_path:
    :type coverage_path: str

    :return:
    :rtype: CoverageData or None
    """
    print("Using coverage data at: '{}'".format(coverage_path))
    # noinspection PyPackageRequirements,PyUnresolvedReferences
    import coverage
    coverage_data = coverage.CoverageData()
    coverage_data.read_file(coverage_path)
    assert coverage_data
    return coverage_data


def get_python_source_files(path, tests_dirs):
    """Yield the paths to all python source files

    :param path: path of the source file to mutate or path of the directory to
        yield source files from to mutate
    :type path: str

    :param tests_dirs: list of the directories containing testing files
    :type tests_dirs: list[str]

    :return:
    :rtype:
    """
    if os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if
                       os.path.join(root, d) not in tests_dirs]
            for filename in files:
                if filename.endswith('.py'):
                    yield os.path.join(root, filename)
    else:
        yield path


def get_tests_dirs(tests_dir, paths_to_mutate) -> list:
    """Get the paths of all testing files/directories

    :param tests_dir:
    :type tests_dir: list[str]

    :param paths_to_mutate:
    :type paths_to_mutate: list[str]

    :return:
    :rtype: list[str]
    """
    full_tests_dirs = []
    for p in tests_dir:
        full_tests_dirs.extend(glob(p, recursive=True))

    for p in paths_to_mutate:
        for pt in tests_dir:
            full_tests_dirs.extend(glob(p + '/**/' + pt, recursive=True))

    return full_tests_dirs
