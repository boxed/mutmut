# -*- coding: utf-8 -*-
from __future__ import annotations

import fnmatch
import itertools
import multiprocessing
import os
import shlex
import subprocess
import sys
import toml
from configparser import ConfigParser
from copy import copy as copy_obj
from functools import wraps
from io import (
    open,
    TextIOBase,
)
from os.path import isdir
from shutil import (
    move,
    copy,
)
from threading import (
    Timer,
    Thread,
)
from time import time
from typing import Callable, Dict, Iterator, List, Optional, Set

__version__ = '2.4.5'

from mutmut.helpers.relativemutationid import RelativeMutationID
from mutmut.helpers.context import Context, ALL
from mutmut.helpers.config import Config
from mutmut.helpers.progress import *
from mutmut.mutator import mutate_file, list_mutations
from mutmut.tester import *

if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())
try:
    import mutmut_config
except ImportError:
    mutmut_config = None



def config_from_file(**defaults):
    def config_from_pyproject_toml() -> dict:
        try:
            return toml.load('pyproject.toml')['tool']['mutmut']
        except (FileNotFoundError, KeyError):
            return {}

    def config_from_setup_cfg() -> dict:
        config_parser = ConfigParser()
        config_parser.read('setup.cfg')

        try:
            return dict(config_parser['mutmut'])
        except KeyError:
            return {}

    config = config_from_pyproject_toml() or config_from_setup_cfg()

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            for k in list(kwargs.keys()):
                if not kwargs[k]:
                    kwargs[k] = config.get(k, defaults.get(k))
            f(*args, **kwargs)

        return wrapper

    return decorator


def guess_paths_to_mutate() -> str:
    """Guess the path to source code to mutate"""
    this_dir = os.getcwd().split(os.sep)[-1]
    if isdir('lib'):
        return 'lib'
    elif isdir('src'):
        return 'src'
    elif isdir(this_dir):
        return this_dir
    elif isdir(this_dir.replace('-', '_')):
        return this_dir.replace('-', '_')
    elif isdir(this_dir.replace(' ', '_')):
        return this_dir.replace(' ', '_')
    elif isdir(this_dir.replace('-', '')):
        return this_dir.replace('-', '')
    elif isdir(this_dir.replace(' ', '')):
        return this_dir.replace(' ', '')
    raise FileNotFoundError(
        'Could not figure out where the code to mutate is. '
        'Please specify it on the command line using --paths-to-mutate, '
        'or by adding "paths_to_mutate=code_dir" in pyproject.toml or setup.cfg to the [mutmut] '
        'section.')


def check_coverage_data_filepaths(coverage_data):
    for filepath in coverage_data:
        if not os.path.exists(filepath):
            raise ValueError('Filepaths in .coverage not recognized, try recreating the .coverage file manually.')


def get_mutations_by_file_from_cache(mutation_pk):
    from mutmut.cache import filename_and_mutation_id_from_pk
    filename, mutation_id = filename_and_mutation_id_from_pk(int(mutation_pk))
    return {filename: [mutation_id]}


def read_coverage_data() -> Dict[str, Dict[int, List[str]]]:
    """
    Reads the coverage database and returns a dictionary which maps the filenames to the covered lines and their contexts.
    """
    try:
        # noinspection PyPackageRequirements,PyUnresolvedReferences
        from coverage import Coverage
    except ImportError as e:
        raise ImportError(
            'The --use-coverage feature requires the coverage library. Run "pip install --force-reinstall mutmut[coverage]"') from e
    cov = Coverage('.coverage')
    cov.load()
    data = cov.get_data()
    return {filepath: data.contexts_by_lineno(filepath) for filepath in data.measured_files()}


def read_patch_data(patch_file_path: str):
    try:
        # noinspection PyPackageRequirements
        import whatthepatch
    except ImportError as e:
        raise ImportError(
            'The --use-patch feature requires the whatthepatch library. Run "pip install --force-reinstall mutmut[patch]"') from e
    with open(patch_file_path) as f:
        diffs = whatthepatch.parse_patch(f.read())

    return {
        os.path.normpath(diff.header.new_path): {change.new for change in diff.changes if change.old is None}
        for diff in diffs if diff.changes
    }


def add_mutations_by_file(
        mutations_by_file: Dict[str, List[RelativeMutationID]],
        filename: str,
        dict_synonyms: List[str],
        config: Optional[Config],
):
    with open(filename) as f:
        source = f.read()
    context = Context(
        source=source,
        filename=filename,
        config=config,
        dict_synonyms=dict_synonyms,
    )

    try:
        mutations_by_file[filename] = list_mutations(context)
        from mutmut.cache import register_mutants

        register_mutants(mutations_by_file)
    except Exception as e:
        raise RuntimeError(
            'Failed while creating mutations for {}, for line "{}"'.format(
                context.filename, context.current_source_line
            )
        ) from e


def python_source_files(
        path: str, tests_dirs: List[str], paths_to_exclude: Optional[List[str]] = None
) -> Iterator[str]:
    """Attempt to guess where the python source files to mutate are and yield
    their paths

    :param path: path to a python source file or package directory
    :param tests_dirs: list of directory paths containing test files
        (we do not want to mutate these!)
    :param paths_to_exclude: list of UNIX filename patterns to exclude

    :return: generator listing the paths to the python source files to mutate
    """
    paths_to_exclude = paths_to_exclude or []
    if isdir(path):
        for root, dirs, files in os.walk(path, topdown=True):
            for exclude_pattern in paths_to_exclude:
                dirs[:] = [d for d in dirs if not fnmatch.fnmatch(d, exclude_pattern)]
                files[:] = [f for f in files if not fnmatch.fnmatch(f, exclude_pattern)]

            dirs[:] = [d for d in dirs if os.path.join(root, d) not in tests_dirs]
            for filename in files:
                if filename.endswith('.py'):
                    yield os.path.join(root, filename)
    else:
        yield path


def compute_exit_code(
        progress: Progress, exception: Optional[Exception] = None, ci: bool = False
) -> int:
    """Compute an exit code for mutmut mutation testing

    The following exit codes are available for mutmut (as documented for the CLI run command):
     * 0 if all mutants were killed (OK_KILLED)
     * 1 if a fatal error occurred
     * 2 if one or more mutants survived (BAD_SURVIVED)
     * 4 if one or more mutants timed out (BAD_TIMEOUT)
     * 8 if one or more mutants caused tests to take twice as long (OK_SUSPICIOUS)

     Exit codes 1 to 8 will be bit-ORed so that it is possible to know what
     different mutant statuses occurred during mutation testing.

     When running with ci=True (--CI flag enabled), the exit code will always be
     1 for a fatal error or 0 for any other case.

    :param exception:
    :param progress:
    :param ci:

    :return: integer noting the exit code of the mutation tests.
    """
    code = 0
    if exception is not None:
        code = code | 1
    if ci:
        return code
    if progress.surviving_mutants > 0:
        code = code | 2
    if progress.surviving_mutants_timeout > 0:
        code = code | 4
    if progress.suspicious_mutants > 0:
        code = code | 8
    return code









