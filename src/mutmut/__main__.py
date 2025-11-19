import ast
import fnmatch
import gc
import inspect
import itertools
import json
from multiprocessing import Pool, set_start_method, Lock
import os
import resource
import shutil
import signal
import subprocess
import sys
from abc import ABC
from collections import defaultdict
from configparser import (
    ConfigParser,
    NoOptionError,
    NoSectionError,
)
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
)
from difflib import unified_diff
from io import TextIOBase
from json import JSONDecodeError
from math import ceil
from os import (
    makedirs,
    walk,
)
from os.path import (
    isdir,
    isfile,
)
from pathlib import Path
from signal import SIGTERM
from threading import Thread
from time import (
    process_time,
    sleep,
)
from typing import (
    Dict,
    List,
    Union,
    Optional,
)
import warnings

import click
import libcst as cst
import libcst.matchers as m
from rich.text import Text
from setproctitle import setproctitle

import mutmut
from mutmut.code_coverage import gather_coverage, get_covered_lines_for_file
from mutmut.file_mutation import mutate_file_contents
from mutmut.trampoline_templates import CLASS_NAME_SEPARATOR

# Document: surviving mutants are retested when you ask mutmut to retest them, interactively in the UI or via command line

# TODO: pragma no mutate should end up in `skipped` category
# TODO: hash of function. If hash changes, retest all mutants as mutant IDs are not stable


status_by_exit_code = defaultdict(lambda: 'suspicious', {
    1: 'killed',
    3: 'killed',  # internal error in pytest means a kill
    -24: 'killed',
    0: 'survived',
    5: 'no tests',
    2: 'check was interrupted by user',
    None: 'not checked',
    33: 'no tests',
    34: 'skipped',
    35: 'suspicious',
    36: 'timeout',
    -24: 'timeout',  # SIGXCPU
    24: 'timeout',  # SIGXCPU
    152: 'timeout',  # SIGXCPU
    255: 'timeout',
    -11: 'segfault',
    -9: 'segfault',
})

emoji_by_status = {
    'survived': '🙁',
    'no tests': '🫥',
    'timeout': '⏰',
    'suspicious': '🤔',
    'skipped': '🔇',
    'check was interrupted by user': '🛑',
    'not checked': '?',
    'killed': '🎉',
    'segfault': '💥',
}

exit_code_to_emoji = {
    exit_code: emoji_by_status[status]
    for exit_code, status in status_by_exit_code.items()
}


def guess_paths_to_mutate():
    """Guess the path to source code to mutate

    :rtype: str
    """
    this_dir = os.getcwd().split(os.sep)[-1]
    if isdir('lib'):
        return ['lib']
    elif isdir('src'):
        return ['src']
    elif isdir(this_dir):
        return [this_dir]
    elif isdir(this_dir.replace('-', '_')):
        return [this_dir.replace('-', '_')]
    elif isdir(this_dir.replace(' ', '_')):
        return [this_dir.replace(' ', '_')]
    elif isdir(this_dir.replace('-', '')):
        return [this_dir.replace('-', '')]
    elif isdir(this_dir.replace(' ', '')):
        return [this_dir.replace(' ', '')]
    if isfile(this_dir + '.py'):
        return [this_dir + '.py']
    raise FileNotFoundError(
        'Could not figure out where the code to mutate is. '
        'Please specify it by adding "paths_to_mutate=code_dir" in setup.cfg to the [mutmut] section.')


def record_trampoline_hit(name):
    assert not name.startswith('src.'), f'Failed trampoline hit. Module name starts with `src.`, which is invalid'
    if mutmut.config.max_stack_depth != -1:
        f = inspect.currentframe()
        c = mutmut.config.max_stack_depth
        while c and f:
            filename = f.f_code.co_filename
            if 'pytest' in filename or 'hammett' in filename or 'unittest' in filename:
                break
            f = f.f_back
            c -= 1

        if not c:
            return

    mutmut._stats.add(name)


def walk_all_files():
    for path in mutmut.config.paths_to_mutate:
        if not isdir(path):
            if isfile(path):
                yield '', str(path)
                continue
        for root, dirs, files in walk(path):
            for filename in files:
                yield root, filename


def walk_source_files():
    for root, filename in walk_all_files():
        if filename.endswith('.py'):
            yield Path(root) / filename


class MutmutProgrammaticFailException(Exception):
    pass


class CollectTestsFailedException(Exception):
    pass


class BadTestExecutionCommandsException(Exception):
    def __init__(self, pytest_args: list[str]) -> None:
        msg = f'Failed to run pytest with args: {pytest_args}. If your config sets debug=true, the original pytest error should be above.'
        super().__init__(msg)


class InvalidGeneratedSyntaxException(Exception):
    def __init__(self, file: Union[Path, str]) -> None:
        super().__init__(f'Mutmut generated invalid python syntax for {file}. '
                          'If the original file has valid python syntax, please file an issue '
                          'with a minimal reproducible example file.')


def copy_src_dir():
    for path in mutmut.config.paths_to_mutate:
        output_path: Path = Path('mutants') / path
        if isdir(path):
            shutil.copytree(path, output_path, dirs_exist_ok=True)
        else:
            output_path.parent.mkdir(exist_ok=True, parents=True)
            shutil.copyfile(path, output_path)

@dataclass
class FileMutationResult:
    """Dataclass to transfer warnings and errors from child processes to the parent"""
    warnings: list[Warning]
    error: Optional[Exception] = None

def create_mutants(max_children: int):
    with Pool(processes=max_children) as p:
        for result in p.imap_unordered(create_file_mutants, walk_source_files()):
            for warning in result.warnings:
                warnings.warn(warning)
            if result.error:
                raise result.error

def create_file_mutants(path: Path) -> FileMutationResult:
    try:
        print(path)
        output_path = Path('mutants') / path
        makedirs(output_path.parent, exist_ok=True)

        if mutmut.config.should_ignore_for_mutation(path):
            shutil.copy(path, output_path)
            return FileMutationResult(warnings=[])
        else:
            return create_mutants_for_file(path, output_path)
    except Exception as e:
        return FileMutationResult(warnings=[], error=e)

def setup_source_paths():
    # ensure that the mutated source code can be imported by the tests
    source_code_paths = [Path('.'), Path('src'), Path('source')]
    for path in source_code_paths:
        mutated_path = Path('mutants') / path
        if mutated_path.exists():
            sys.path.insert(0, str(mutated_path.absolute()))

    # ensure that the original code CANNOT be imported by the tests
    for path in source_code_paths:
        for i in range(len(sys.path)):
            while i < len(sys.path) and Path(sys.path[i]).resolve() == path.resolve():
                del sys.path[i]

def store_lines_covered_by_tests():
    if mutmut.config.mutate_only_covered_lines:
        mutmut._covered_lines = gather_coverage(PytestRunner(), list(walk_source_files()))

def copy_also_copy_files():
    assert isinstance(mutmut.config.also_copy, list)
    for path in mutmut.config.also_copy:
        print('     also copying', path)
        path = Path(path)
        destination = Path('mutants') / path
        if not path.exists():
            continue
        if path.is_file():
            shutil.copy(path, destination)
        else:
            shutil.copytree(path, destination, dirs_exist_ok=True)

def create_mutants_for_file(filename, output_path) -> FileMutationResult:
    input_stat = os.stat(filename)
    warnings: list[Warning] = []

    with open(filename) as f:
        source = f.read()

    with open(output_path, 'w') as out:
        try:
            mutant_names, hash_by_function_name = write_all_mutants_to_file(out=out, source=source, filename=filename)
        except cst.ParserSyntaxError as e:
            # if libcst cannot parse it, then copy the source without any mutations
            warnings.append(SyntaxWarning(f'Unsupported syntax in {filename} ({str(e)}), skipping'))
            out.write(source)
            mutant_names, hash_by_function_name = [], {}

    # validate no syntax errors of mutants
    with open(output_path) as f:
        try:
            ast.parse(f.read())
        except (IndentationError, SyntaxError) as e:
            invalid_syntax_error = InvalidGeneratedSyntaxException(output_path)
            invalid_syntax_error.__cause__ = e
            return FileMutationResult(warnings=warnings, error=invalid_syntax_error)

    source_file_mutation_data = SourceFileMutationData(path=filename)
    module_name = strip_prefix(str(filename)[:-len(filename.suffix)].replace(os.sep, '.'), prefix='src.')

    source_file_mutation_data.exit_code_by_key = {
         '.'.join([module_name, x]).replace('.__init__.', '.'): None
        for x in mutant_names
    }
    source_file_mutation_data.hash_by_function_name = hash_by_function_name
    assert None not in hash_by_function_name
    source_file_mutation_data.save()

    os.utime(output_path, (input_stat.st_atime, input_stat.st_mtime))
    return FileMutationResult(warnings=warnings)


def write_all_mutants_to_file(*, out, source, filename):
    result, mutant_names = mutate_file_contents(filename, source, get_covered_lines_for_file(filename, mutmut._covered_lines))
    out.write(result)

    # TODO: function hashes are currently not used. Reimplement this when needed.
    hash_by_function_name = {}

    return mutant_names, hash_by_function_name


class SourceFileMutationData:
    def __init__(self, *, path):
        self.estimated_time_of_tests_by_mutant = {}
        self.path = path
        self.meta_path = Path('mutants') / (str(path) + '.meta')
        self.key_by_pid = {}
        self.exit_code_by_key = {}
        self.durations_by_key = {}
        self.hash_by_function_name = {}
        self.start_time_by_pid = {}

    def load(self):
        try:
            with open(self.meta_path) as f:
                meta = json.load(f)
        except FileNotFoundError:
            return

        self.exit_code_by_key = meta.pop('exit_code_by_key')
        self.hash_by_function_name = meta.pop('hash_by_function_name')
        self.durations_by_key = meta.pop('durations_by_key')
        self.estimated_time_of_tests_by_mutant = meta.pop('estimated_durations_by_key')
        assert not meta, f'Meta file {self.meta_path} constains unexpected keys: {set(meta.keys())}'

    def register_pid(self, *, pid, key):
        self.key_by_pid[pid] = key
        with START_TIMES_BY_PID_LOCK:
            self.start_time_by_pid[pid] = datetime.now()

    def register_result(self, *, pid, exit_code):
        assert self.key_by_pid[pid] in self.exit_code_by_key
        key = self.key_by_pid[pid]
        self.exit_code_by_key[key] = exit_code
        self.durations_by_key[key] = (datetime.now() - self.start_time_by_pid[pid]).total_seconds()
        # TODO: maybe rate limit this? Saving on each result can slow down mutation testing a lot if the test run is fast.
        del self.key_by_pid[pid]
        with START_TIMES_BY_PID_LOCK:
            del self.start_time_by_pid[pid]
        self.save()

    def stop_children(self):
        for pid in self.key_by_pid.keys():
            os.kill(pid, SIGTERM)

    def save(self):
        with open(self.meta_path, 'w') as f:
            json.dump(dict(
                exit_code_by_key=self.exit_code_by_key,
                hash_by_function_name=self.hash_by_function_name,
                durations_by_key=self.durations_by_key,
                estimated_durations_by_key=self.estimated_time_of_tests_by_mutant,
            ), f, indent=4)


def unused(*_):
    pass


def strip_prefix(s, *, prefix, strict=False):
    if s.startswith(prefix):
        return s[len(prefix):]
    assert strict is False, f"String '{s}' does not start with prefix '{prefix}'"
    return s


class TestRunner(ABC):
    def run_stats(self, *, tests):
        raise NotImplementedError()

    def run_forced_fail(self):
        raise NotImplementedError()

    def prepare_main_test_run(self):
        pass

    def run_tests(self, *, mutant_name, tests):
        raise NotImplementedError()

    def list_all_tests(self):
        raise NotImplementedError()


@contextmanager
def change_cwd(path):
    old_cwd = os.path.abspath(os.getcwd())
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def collected_test_names():
    return set(mutmut.duration_by_test.keys())


class ListAllTestsResult:
    def __init__(self, *, ids):
        assert isinstance(ids, set)
        self.ids = ids

    def clear_out_obsolete_test_names(self):
        count_before = sum(len(x) for x in mutmut.tests_by_mangled_function_name)
        mutmut.tests_by_mangled_function_name = defaultdict(set, **{
            k: {test_name for test_name in test_names if test_name in self.ids}
            for k, test_names in mutmut.tests_by_mangled_function_name.items()
        })
        count_after = sum(len(x) for x in mutmut.tests_by_mangled_function_name)
        if count_before != count_after:
            print(f'Removed {count_before - count_after} obsolete test names')
            save_stats()

    def new_tests(self):
        return self.ids - collected_test_names()


class PytestRunner(TestRunner):
    def __init__(self):
        self._pytest_add_cli_args: List[str] = mutmut.config.pytest_add_cli_args
        self._pytest_add_cli_args_test_selection: List[str] = mutmut.config.pytest_add_cli_args_test_selection

        # tests_dir is a special case of a test selection option,
        # so also use pytest_add_cli_args_test_selection for the implementation
        self._pytest_add_cli_args_test_selection += mutmut.config.tests_dir


    # noinspection PyMethodMayBeStatic
    def execute_pytest(self, params: list[str], **kwargs):
        import pytest
        params = ['--rootdir=.', '--tb=native'] + params + self._pytest_add_cli_args
        if mutmut.config.debug:
            params = ['-vv'] + params
            print('python -m pytest ', ' '.join([f'"{param}"' for param in params]))
        exit_code = int(pytest.main(params, **kwargs))
        if mutmut.config.debug:
            print('    exit code', exit_code)
        if exit_code == 4:
            raise BadTestExecutionCommandsException(params)
        return exit_code

    def run_stats(self, *, tests):
        class StatsCollector:
            # noinspection PyMethodMayBeStatic
            def pytest_runtest_logstart(self, nodeid, location):
                mutmut.duration_by_test[nodeid] = 0

            # noinspection PyMethodMayBeStatic
            def pytest_runtest_teardown(self, item, nextitem):
                unused(nextitem)
                for function in mutmut._stats:
                    mutmut.tests_by_mangled_function_name[function].add(strip_prefix(item._nodeid, prefix='mutants/'))
                mutmut._stats.clear()

            # noinspection PyMethodMayBeStatic
            def pytest_runtest_makereport(self, item, call):
                mutmut.duration_by_test[item.nodeid] += call.duration

        stats_collector = StatsCollector()

        pytest_args = ['-x', '-q']
        if tests:
            pytest_args += list(tests)
        else:
            pytest_args += self._pytest_add_cli_args_test_selection
        with change_cwd('mutants'):
            return int(self.execute_pytest(pytest_args, plugins=[stats_collector]))

    def run_tests(self, *, mutant_name, tests):
        pytest_args = ['-x', '-q', '-p', 'no:randomly', '-p', 'no:random-order']
        if tests:
            pytest_args += list(tests)
        else:
            pytest_args += self._pytest_add_cli_args_test_selection
        with change_cwd('mutants'):
            return int(self.execute_pytest(pytest_args))

    def run_forced_fail(self):
        pytest_args = ['-x', '-q'] + self._pytest_add_cli_args_test_selection
        with change_cwd('mutants'):
            return int(self.execute_pytest(pytest_args))

    def list_all_tests(self):
        class TestsCollector:
            def __init__(self):
                self.collected_nodeids = set()
                self.deselected_nodeids = set()

            def pytest_collection_modifyitems(self, items):
                self.collected_nodeids |= {item.nodeid for item in items}

            def pytest_deselected(self, items):
                self.deselected_nodeids |= {item.nodeid for item in items}

        collector = TestsCollector()

        tests_dir = mutmut.config.tests_dir
        pytest_args = ['-x', '-q', '--collect-only'] + self._pytest_add_cli_args_test_selection

        with change_cwd('mutants'):
            exit_code = int(self.execute_pytest(pytest_args, plugins=[collector]))
            if exit_code != 0:
                raise CollectTestsFailedException()

        selected_nodeids = collector.collected_nodeids - collector.deselected_nodeids
        return ListAllTestsResult(ids=selected_nodeids)


class HammettRunner(TestRunner):
    def __init__(self):
        self.hammett_kwargs = None

    def run_stats(self, *, tests):
        import hammett
        print('Running hammett stats...')

        def post_test_callback(_name, **_):
            for function in mutmut._stats:
                mutmut.tests_by_mangled_function_name[function].add(_name)
            mutmut._stats.clear()

        return hammett.main(quiet=True, fail_fast=True, disable_assert_analyze=True, post_test_callback=post_test_callback, use_cache=False, insert_cwd=False)

    def run_forced_fail(self):
        import hammett
        return hammett.main(quiet=True, fail_fast=True, disable_assert_analyze=True, use_cache=False, insert_cwd=False)

    def prepare_main_test_run(self):
        import hammett
        self.hammett_kwargs = hammett.main_setup(
            quiet=True,
            fail_fast=True,
            disable_assert_analyze=True,
            use_cache=False,
            insert_cwd=False,
        )

    def run_tests(self, *, mutant_name, tests):
        import hammett
        hammett.Config.workerinput = dict(workerinput=f'_{mutant_name}')
        return hammett.main_run_tests(**self.hammett_kwargs, tests=tests)


def mangled_name_from_mutant_name(mutant_name):
    assert '__mutmut_' in mutant_name, mutant_name
    return mutant_name.partition('__mutmut_')[0]


def orig_function_and_class_names_from_key(mutant_name):
    r = mangled_name_from_mutant_name(mutant_name)
    _, _, r = r.rpartition('.')
    class_name = None
    if CLASS_NAME_SEPARATOR in r:
        class_name = r[r.index(CLASS_NAME_SEPARATOR) + 1: r.rindex(CLASS_NAME_SEPARATOR)]
        r = r[r.rindex(CLASS_NAME_SEPARATOR) + 1:]
    else:
        assert r.startswith('x_'), r
        r = r[2:]
    return r, class_name


spinner = itertools.cycle('⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏')


def status_printer():
    """Manage the printing and in-place updating of a line of characters

    .. note::
        If the string is longer than a line, then in-place updating may not
        work (it will print a new line at each refresh).
    """
    last_len = [0]
    last_update = [datetime(1900, 1, 1)]
    update_threshold = timedelta(seconds=0.1)

    def p(s, *, force_output=False):
        if not force_output and (datetime.now() - last_update[0]) < update_threshold:
            return
        s = next(spinner) + ' ' + s
        len_s = len(s)
        output = '\r' + s + (' ' * max(last_len[0] - len_s, 0))
        sys.__stdout__.write(output)
        sys.__stdout__.flush()
        last_len[0] = len_s
    return p


print_status = status_printer()


@dataclass
class Stat:
    not_checked: int
    killed: int
    survived: int
    total: int
    no_tests: int
    skipped: int
    suspicious: int
    timeout: int
    check_was_interrupted_by_user: int
    segfault: int


def collect_stat(m: SourceFileMutationData):
    r = {
        k.replace(' ', '_'): 0
        for k in status_by_exit_code.values()
    }
    for k, v in m.exit_code_by_key.items():
        # noinspection PyTypeChecker
        r[status_by_exit_code[v].replace(' ', '_')] += 1
    return Stat(
        **r,
        total=sum(r.values()),
    )


def calculate_summary_stats(source_file_mutation_data_by_path):
    stats = [collect_stat(x) for x in source_file_mutation_data_by_path.values()]
    return Stat(
        not_checked=sum(x.not_checked for x in stats),
        killed=sum(x.killed for x in stats),
        survived=sum(x.survived for x in stats),
        total=sum(x.total for x in stats),
        no_tests=sum(x.no_tests for x in stats),
        skipped=sum(x.skipped for x in stats),
        suspicious=sum(x.suspicious for x in stats),
        timeout=sum(x.timeout for x in stats),
        check_was_interrupted_by_user=sum(x.check_was_interrupted_by_user for x in stats),
        segfault=sum(x.segfault for x in stats),
    )


def print_stats(source_file_mutation_data_by_path, force_output=False):
    s = calculate_summary_stats(source_file_mutation_data_by_path)
    print_status(f'{(s.total - s.not_checked)}/{s.total}  🎉 {s.killed} 🫥 {s.no_tests}  ⏰ {s.timeout}  🤔 {s.suspicious}  🙁 {s.survived}  🔇 {s.skipped}', force_output=force_output)


def run_forced_fail_test(runner):
    os.environ['MUTANT_UNDER_TEST'] = 'fail'
    with CatchOutput(spinner_title='Running forced fail test') as catcher:
        try:
            if runner.run_forced_fail() == 0:
                catcher.dump_output()
                print("FAILED: Unable to force test failures")
                raise SystemExit(1)
        except MutmutProgrammaticFailException:
            pass
    os.environ['MUTANT_UNDER_TEST'] = ''
    print('    done')


class CatchOutput:
    def __init__(self, callback=lambda s: None, spinner_title=None):
        self.strings = []
        self.spinner_title = spinner_title or ''
        if mutmut.config is not None and mutmut.config.debug:
            self.spinner_title += '\n'

        class StdOutRedirect(TextIOBase):
            def __init__(self, catcher):
                self.catcher = catcher

            def write(self, s):
                callback(s)
                if spinner_title:
                    print_status(spinner_title)
                self.catcher.strings.append(s)
                return len(s)
        self.redirect = StdOutRedirect(self)

    # noinspection PyMethodMayBeStatic
    def stop(self):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    def start(self):
        if self.spinner_title:
            print_status(self.spinner_title)
        sys.stdout = self.redirect
        sys.stderr = self.redirect
        if mutmut.config.debug:
            self.stop()

    def dump_output(self):
        self.stop()
        print()
        for line in self.strings:
            print(line, end='')

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        if self.spinner_title:
            print()


@dataclass
class Config:
    also_copy: List[Path]
    do_not_mutate: List[str]
    max_stack_depth: int
    debug: bool
    paths_to_mutate: List[Path]
    pytest_add_cli_args: List[str]
    pytest_add_cli_args_test_selection: List[str]
    tests_dir: List[str]
    mutate_only_covered_lines: bool

    def should_ignore_for_mutation(self, path):
        if not str(path).endswith('.py'):
            return True
        for p in self.do_not_mutate:
            if fnmatch.fnmatch(path, p):
                return True
        return False


def config_reader():
    path = Path('pyproject.toml')
    if path.exists():
        if sys.version_info >= (3, 11):
            from tomllib import loads
        else:
            # noinspection PyPackageRequirements
            from toml import loads
        data = loads(path.read_text('utf-8'))

        try:
            config = data['tool']['mutmut']
        except KeyError:
            pass
        else:
            def s(key, default):
                try:
                    result = config[key]
                except KeyError:
                    return default
                return result
            return s

    config_parser = ConfigParser()
    config_parser.read('setup.cfg')

    def s(key: str, default):
        try:
            result = config_parser.get('mutmut', key)
        except (NoOptionError, NoSectionError):
            return default
        if isinstance(default, list):
            if '\n' in result:
                result = [x for x in result.split("\n") if x]
            else:
                result = [result]
        elif isinstance(default, bool):
            result = result.lower() in ('1', 't', 'true')
        elif isinstance(default, int):
            result = int(result)
        return result
    return s


def ensure_config_loaded():
    if mutmut.config is None:
        mutmut.config = load_config()


def load_config():
    s = config_reader()

    return Config(
        do_not_mutate=s('do_not_mutate', []),
        also_copy=[
            Path(y)
            for y in s('also_copy', [])
        ] + [
            Path('tests/'),
            Path('test/'),
            Path('setup.cfg'),
            Path('pyproject.toml'),
        ] + list(Path('.').glob('test*.py')),
        max_stack_depth=s('max_stack_depth', -1),
        debug=s('debug', False),
        mutate_only_covered_lines=s('mutate_only_covered_lines', False),
        paths_to_mutate=[
            Path(y)
            for y in s('paths_to_mutate', [])
        ] or guess_paths_to_mutate(),
        tests_dir=s('tests_dir', []),
        pytest_add_cli_args=s('pytest_add_cli_args', []),
        pytest_add_cli_args_test_selection=s('pytest_add_cli_args_test_selection', []),
    )



@click.group()
@click.version_option()
def cli():
    pass


def run_stats_collection(runner, tests=None):
    if tests is None:
        tests = []  # Meaning all...

    os.environ['MUTANT_UNDER_TEST'] = 'stats'
    os.environ['PY_IGNORE_IMPORTMISMATCH'] = '1'
    start_cpu_time = process_time()

    with CatchOutput(spinner_title='Running stats') as output_catcher:
        collect_stats_exit_code = runner.run_stats(tests=tests)
        if collect_stats_exit_code != 0:
            output_catcher.dump_output()
            print(f'failed to collect stats. runner returned {collect_stats_exit_code}')
            exit(1)
        # ensure that at least one mutant has associated tests
        num_associated_tests = sum(len(tests) for tests in mutmut.tests_by_mangled_function_name.values())
        if num_associated_tests == 0:
            output_catcher.dump_output()
            print('Stopping early, because we could not find any test case for any mutant. It seems that the selected tests do not cover any code that we mutated.')
            if not mutmut.config.debug:
                print('You can set debug=true to see the executed test names in the output above.')
            else:
                print('In the last pytest run above, you can see which tests we executed.')
            print('You can use mutmut browse to check which parts of the source code we mutated.')
            print('If some of the mutated code should be covered by the executed tests, consider opening an issue (with a MRE if possible).')
            exit(1)

    print('    done')
    if not tests:  # again, meaning all
        mutmut.stats_time = process_time() - start_cpu_time

    if not collected_test_names():
        print('failed to collect stats, no active tests found')
        exit(1)

    save_stats()


def collect_or_load_stats(runner):
    did_load = load_stats()

    if not did_load:
        # Run full stats
        run_stats_collection(runner)
    else:
        # Run incremental stats
        with CatchOutput(spinner_title='Listing all tests') as output_catcher:
            os.environ['MUTANT_UNDER_TEST'] = 'list_all_tests'
            try:
                all_tests_result = runner.list_all_tests()
            except CollectTestsFailedException:
                output_catcher.dump_output()
                print('Failed to collect list of tests')
                exit(1)

        all_tests_result.clear_out_obsolete_test_names()

        new_tests = all_tests_result.new_tests()

        if new_tests:
            print(f'Found {len(new_tests)} new tests, rerunning stats collection')
            run_stats_collection(runner, tests=new_tests)


def load_stats():
    did_load = False
    try:
        with open('mutants/mutmut-stats.json') as f:
            data = json.load(f)
            for k, v in data.pop('tests_by_mangled_function_name').items():
                mutmut.tests_by_mangled_function_name[k] |= set(v)
            mutmut.duration_by_test = data.pop('duration_by_test')
            mutmut.stats_time = data.pop('stats_time')
            assert not data, data
            did_load = True
    except (FileNotFoundError, JSONDecodeError):
        pass
    return did_load


def save_stats():
    with open('mutants/mutmut-stats.json', 'w') as f:
        json.dump(dict(
            tests_by_mangled_function_name={k: list(v) for k, v in mutmut.tests_by_mangled_function_name.items()},
            duration_by_test=mutmut.duration_by_test,
            stats_time=mutmut.stats_time,
        ), f, indent=4)


def collect_source_file_mutation_data(*, mutant_names):
    source_file_mutation_data_by_path: Dict[str, SourceFileMutationData] = {}

    for path in walk_source_files():
        if mutmut.config.should_ignore_for_mutation(path):
            continue
        assert path not in source_file_mutation_data_by_path
        m = SourceFileMutationData(path=path)
        m.load()
        source_file_mutation_data_by_path[str(path)] = m

    mutants = [
        (m, mutant_name, result)
        for path, m in source_file_mutation_data_by_path.items()
        for mutant_name, result in m.exit_code_by_key.items()
    ]

    if mutant_names:
        filtered_mutants = [
            (m, key, result)
            for m, key, result in mutants
            if key in mutant_names or any(fnmatch.fnmatch(key, mutant_name) for mutant_name in mutant_names)
        ]
        assert filtered_mutants, f'Filtered for specific mutants, but nothing matches\n\nFilter: {mutant_names}'
        mutants = filtered_mutants
    return mutants, source_file_mutation_data_by_path


def estimated_worst_case_time(mutant_name):
    tests = mutmut.tests_by_mangled_function_name.get(mangled_name_from_mutant_name(mutant_name), set())
    return sum(mutmut.duration_by_test[t] for t in tests)


@cli.command()
@click.argument('mutant_names', required=False, nargs=-1)
def print_time_estimates(mutant_names):
    assert isinstance(mutant_names, (tuple, list)), mutant_names
    ensure_config_loaded()

    runner = PytestRunner()
    runner.prepare_main_test_run()

    collect_or_load_stats(runner)

    mutants, source_file_mutation_data_by_path = collect_source_file_mutation_data(mutant_names=mutant_names)

    times_and_keys = [
        (estimated_worst_case_time(mutant_name), mutant_name)
        for m, mutant_name, result in mutants
    ]

    for time, key in sorted(times_and_keys):
        if not time:
            print(f'<no tests>', key)
        else:
            print(f'{int(time*1000)}ms', key)


@cli.command()
@click.argument('mutant_name', required=True, nargs=1)
def tests_for_mutant(mutant_name):
    if not load_stats():
        print('Failed to load stats. Please run mutmut first to collect stats.')
        exit(1)

    tests = tests_for_mutant_names([mutant_name])
    for test in sorted(tests):
        print(test)


def stop_all_children(mutants):
    for m, _, _ in mutants:
        m.stop_children()

# used to copy the global mutmut.config to subprocesses
set_start_method('fork')
START_TIMES_BY_PID_LOCK = Lock()

def timeout_checker(mutants):
    def inner_timeout_checker():
        while True:
            sleep(1)

            now = datetime.now()
            for m, mutant_name, result in mutants:
                # copy dict inside lock, so it is not modified by another process while we iterate it
                with START_TIMES_BY_PID_LOCK:
                    start_times_by_pid = dict(m.start_time_by_pid)
                for pid, start_time in start_times_by_pid.items():
                    run_time = now - start_time
                    if run_time.total_seconds() > (m.estimated_time_of_tests_by_mutant[mutant_name] + 1) * 15:
                        try:
                            os.kill(pid, signal.SIGXCPU)
                        except ProcessLookupError:
                            pass
    return inner_timeout_checker


@cli.command()
@click.option('--max-children', type=int)
@click.argument('mutant_names', required=False, nargs=-1)
def run(mutant_names, *, max_children):
    assert isinstance(mutant_names, (tuple, list)), mutant_names
    _run(mutant_names, max_children)

# separate function, so we can call it directly from the tests
def _run(mutant_names: Union[tuple, list], max_children: Union[None, int]):
    # TODO: run no-ops once in a while to detect if we get false negatives
    # TODO: we should be able to get information on which tests killed mutants, which means we can get a list of tests and how many mutants each test kills. Those that kill zero mutants are redundant!
    os.environ['MUTANT_UNDER_TEST'] = 'mutant_generation'
    ensure_config_loaded()

    if max_children is None:
        max_children = os.cpu_count() or 4

    start = datetime.now()
    makedirs(Path('mutants'), exist_ok=True)
    with CatchOutput(spinner_title='Generating mutants'):
        copy_src_dir()
        copy_also_copy_files()
        setup_source_paths()
        store_lines_covered_by_tests()            
        create_mutants(max_children)

    time = datetime.now() - start
    print(f'    done in {round(time.total_seconds()*1000)}ms', )

    # TODO: config/option for runner
    # runner = HammettRunner()
    runner = PytestRunner()
    runner.prepare_main_test_run()

    # TODO: run these steps only if we have mutants to test

    collect_or_load_stats(runner)

    mutants, source_file_mutation_data_by_path = collect_source_file_mutation_data(mutant_names=mutant_names)

    os.environ['MUTANT_UNDER_TEST'] = ''
    with CatchOutput(spinner_title='Running clean tests') as output_catcher:
        tests = tests_for_mutant_names(mutant_names)

        clean_test_exit_code = runner.run_tests(mutant_name=None, tests=tests)
        if clean_test_exit_code != 0:
            output_catcher.dump_output()
            print('Failed to run clean test')
            exit(1)
    print('    done')

    # this can't be the first thing, because it can fail deep inside pytest/django setup and then everything is destroyed
    run_forced_fail_test(runner)

    runner.prepare_main_test_run()

    def read_one_child_exit_status():
        pid, wait_status = os.wait()
        exit_code = os.waitstatus_to_exitcode(wait_status)
        if mutmut.config.debug:
            print('    worker exit code', exit_code)
        source_file_mutation_data_by_pid[pid].register_result(pid=pid, exit_code=exit_code)

    source_file_mutation_data_by_pid: Dict[int, SourceFileMutationData] = {}  # many pids map to one MutationData
    running_children = 0
    count_tried = 0

    # Run estimated fast mutants first, calculated as the estimated time for a surviving mutant.
    mutants = sorted(mutants, key=lambda x: estimated_worst_case_time(x[1]))

    gc.freeze()

    start = datetime.now()
    try:
        print('Running mutation testing')

        # Calculate times of tests
        for m, mutant_name, result in mutants:
            mutant_name = mutant_name.replace('__init__.', '')
            tests = mutmut.tests_by_mangled_function_name.get(mangled_name_from_mutant_name(mutant_name), [])
            estimated_time_of_tests = sum(mutmut.duration_by_test[test_name] for test_name in tests)
            m.estimated_time_of_tests_by_mutant[mutant_name] = estimated_time_of_tests

        Thread(target=timeout_checker(mutants), daemon=True).start()

        # Now do mutation
        for m, mutant_name, result in mutants:
            print_stats(source_file_mutation_data_by_path)

            mutant_name = mutant_name.replace('__init__.', '')

            # Rerun mutant if it's explicitly mentioned, but otherwise let the result stand
            if not mutant_names and result is not None:
                continue

            tests = mutmut.tests_by_mangled_function_name.get(mangled_name_from_mutant_name(mutant_name), [])

            # print(tests)
            if not tests:
                m.exit_code_by_key[mutant_name] = 33
                m.save()
                continue

            pid = os.fork()
            if not pid:
                # In the child
                os.environ['MUTANT_UNDER_TEST'] = mutant_name
                setproctitle(f'mutmut: {mutant_name}')

                # Run fast tests first
                tests = sorted(tests, key=lambda test_name: mutmut.duration_by_test[test_name])
                if not tests:
                    os._exit(33)

                estimated_time_of_tests = m.estimated_time_of_tests_by_mutant[mutant_name]
                cpu_time_limit = ceil((estimated_time_of_tests + 1) * 30 + process_time())
                # signal SIGXCPU after <cpu_time_limit>. One second later signal SIGKILL if it is still running
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_time_limit, cpu_time_limit + 1))

                with CatchOutput():
                    result = runner.run_tests(mutant_name=mutant_name, tests=tests)

                if result != 0:
                    # TODO: write failure information to stdout?
                    pass
                os._exit(result)
            else:
                # in the parent
                source_file_mutation_data_by_pid[pid] = m
                m.register_pid(pid=pid, key=mutant_name)
                running_children += 1

            if running_children >= max_children:
                read_one_child_exit_status()
                count_tried += 1
                running_children -= 1

        try:
            while running_children:
                read_one_child_exit_status()
                count_tried += 1
                running_children -= 1
        except ChildProcessError:
            pass
    except KeyboardInterrupt:
        print('Stopping...')
        stop_all_children(mutants)

    t = datetime.now() - start

    print_stats(source_file_mutation_data_by_path, force_output=True)
    print()
    print(f'{count_tried / t.total_seconds():.2f} mutations/second')

    if mutant_names:
        print()
        print('Mutant results')
        print('--------------')
        exit_code_by_key = {}
        # If the user gave a specific list of mutants, print result for these specifically
        for m, mutant_name, result in mutants:
            exit_code_by_key[mutant_name] = m.exit_code_by_key[mutant_name]

        for mutant_name, exit_code in sorted(exit_code_by_key.items()):
            print(emoji_by_status.get(status_by_exit_code[exit_code], '?'), mutant_name)

        print()


def tests_for_mutant_names(mutant_names):
    tests = set()
    for mutant_name in mutant_names:
        if '*' in mutant_name:
            for name, tests_of_this_name in mutmut.tests_by_mangled_function_name.items():
                if fnmatch.fnmatch(name, mutant_name):
                    tests |= set(tests_of_this_name)
        else:
            tests |= set(mutmut.tests_by_mangled_function_name[mangled_name_from_mutant_name(mutant_name)])
    return tests


@cli.command()
@click.option('--all', default=False)
def results(all):
    ensure_config_loaded()
    for path in walk_source_files():
        if not str(path).endswith('.py'):
            continue
        m = SourceFileMutationData(path=path)
        m.load()
        for k, v in m.exit_code_by_key.items():
            status = status_by_exit_code[v]
            if status == 'killed' and not all:
                continue
            print(f'    {k}: {status}')


def read_mutants_module(path) -> cst.Module:
    with open(Path('mutants') / path) as f:
        return cst.parse_module(f.read())


def read_orig_module(path) -> cst.Module:
    with open(path) as f:
        return cst.parse_module(f.read())


def find_top_level_function_or_method(module: cst.Module, name: str) -> Union[cst.FunctionDef, None]:
    name = name.split('.')[-1]
    for child in module.body:
        if isinstance(child, cst.FunctionDef) and child.name.value == name:
            return child
        if isinstance(child, cst.ClassDef) and isinstance(child.body, cst.IndentedBlock):
            for method in child.body.body:
                if isinstance(method, cst.FunctionDef) and method.name.value == name:
                    return method

    return None


def read_original_function(module: cst.Module, mutant_name: str):
    orig_function_name, _ = orig_function_and_class_names_from_key(mutant_name)
    orig_name = mangled_name_from_mutant_name(mutant_name) + '__mutmut_orig'

    result = find_top_level_function_or_method(module, orig_name)
    if not result:
        raise FileNotFoundError(f'Could not find original function "{orig_function_name}"')
    return result.with_changes(name = cst.Name(orig_function_name))


def read_mutant_function(module: cst.Module, mutant_name: str):
    orig_function_name, _ = orig_function_and_class_names_from_key(mutant_name)

    result = find_top_level_function_or_method(module, mutant_name)
    if not result:
        raise FileNotFoundError(f'Could not find original function "{orig_function_name}"')
    return result.with_changes(name = cst.Name(orig_function_name))


def find_mutant(mutant_name):
    for path in walk_source_files():
        if mutmut.config.should_ignore_for_mutation(path):
            continue

        m = SourceFileMutationData(path=path)
        m.load()
        if mutant_name in m.exit_code_by_key:
            return m

    raise FileNotFoundError(f'Could not find mutant {mutant_name}')


def get_diff_for_mutant(mutant_name, source=None, path=None):
    if path is None:
        m = find_mutant(mutant_name)
        path = m.path
        status = status_by_exit_code[m.exit_code_by_key[mutant_name]]
    else:
        status = 'not checked'

    print(f'# {mutant_name}: {status}')

    if source is None:
        module = read_mutants_module(path)
    else:
        module = cst.parse_module(source)
    orig_code = cst.Module([read_original_function(module, mutant_name)]).code.strip()
    mutant_code = cst.Module([read_mutant_function(module, mutant_name)]).code.strip()

    path = str(path)  # difflib requires str, not Path
    return '\n'.join([
        line
        for line in unified_diff(orig_code.split('\n'), mutant_code.split('\n'), fromfile=path, tofile=path, lineterm='')
    ])


@cli.command()
@click.argument('mutant_name')
def show(mutant_name):
    ensure_config_loaded()
    print(get_diff_for_mutant(mutant_name))
    return


@cli.command()
@click.argument('mutant_name')
def apply(mutant_name):
    # try:
    ensure_config_loaded()
    apply_mutant(mutant_name)
    # except FileNotFoundError as e:
    #     print(e)


def apply_mutant(mutant_name):
    path = find_mutant(mutant_name).path

    orig_function_name, class_name = orig_function_and_class_names_from_key(mutant_name)
    orig_function_name = orig_function_name.rpartition('.')[-1]

    orig_module = read_orig_module(path)
    mutants_module = read_mutants_module(path)

    mutant_function = read_mutant_function(mutants_module, mutant_name)
    mutant_function = mutant_function.with_changes(name=cst.Name(orig_function_name))

    original_function = find_top_level_function_or_method(orig_module, orig_function_name)
    if not original_function:
        raise FileNotFoundError(f'Could not apply mutant {mutant_name}')

    new_module: cst.Module = orig_module.deep_replace(original_function, mutant_function) # type: ignore

    with open(path, 'w') as f:
        f.write(new_module.code)


@cli.command()
@click.option("--show-killed", is_flag=True, default=False, help="Display killed mutants.")
def browse(show_killed):
    ensure_config_loaded()

    from textual.app import App
    from textual.containers import Container
    from textual.widgets import Footer
    from textual.widgets import DataTable
    from textual.widgets import Static
    from textual.widget import Widget
    from rich.syntax import Syntax

    class ResultBrowser(App):
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
            ('path', 'Path'),
        ] + [
            (status, Text(emoji, justify='right'))
            for status, emoji in emoji_by_status.items()
        ]

        cursor_type = 'row'
        source_file_mutation_data_and_stat_by_path: dict[str, tuple[SourceFileMutationData, Stat]] = {}

        def compose(self):
            with Container(classes='container'):
                yield DataTable(id='files')
                yield DataTable(id='mutants')
            with Widget(id="diff_view_widget"):
                yield Static(id='description')
                yield Static(id='diff_view')
            yield Footer()

        def on_mount(self):
            # files table
            # noinspection PyTypeChecker
            files_table: DataTable = self.query_one('#files')
            files_table.cursor_type = 'row'
            for key, label in self.columns:
                files_table.add_column(key=key, label=label)

            # mutants table
            # noinspection PyTypeChecker
            mutants_table: DataTable = self.query_one('#mutants')
            mutants_table.cursor_type = 'row'
            mutants_table.add_columns('name', 'status')

            self.read_data()
            self.populate_files_table()

        def read_data(self):
            ensure_config_loaded()
            self.source_file_mutation_data_and_stat_by_path = {}
            self.path_by_name = {}

            for p in walk_source_files():
                if mutmut.config.should_ignore_for_mutation(p):
                    continue
                source_file_mutation_data = SourceFileMutationData(path=p)
                source_file_mutation_data.load()
                stat = collect_stat(source_file_mutation_data)

                self.source_file_mutation_data_and_stat_by_path[str(p)] = source_file_mutation_data, stat
                for name in source_file_mutation_data.exit_code_by_key:
                    self.path_by_name[name] = p

        def populate_files_table(self):
            # noinspection PyTypeChecker
            files_table: DataTable = self.query_one('#files')
            # TODO: restore selection
            selected_row = files_table.cursor_row
            files_table.clear()

            for p, (source_file_mutation_data, stat) in sorted(self.source_file_mutation_data_and_stat_by_path.items()):
                row = [p] + [
                    Text(str(getattr(stat, k.replace(' ', '_'))), justify="right")
                    for k, _ in self.columns[1:]
                ]
                files_table.add_row(*row, key=str(p))

            files_table.move_cursor(row=selected_row)

        def on_data_table_row_highlighted(self, event):
            if not event.row_key or not event.row_key.value:
                return
            if event.data_table.id == 'files':
                # noinspection PyTypeChecker
                mutants_table: DataTable = self.query_one('#mutants')
                mutants_table.clear()
                source_file_mutation_data, stat = self.source_file_mutation_data_and_stat_by_path[event.row_key.value]
                for k, v in source_file_mutation_data.exit_code_by_key.items():
                    status = status_by_exit_code[v]
                    if status != 'killed' or show_killed:
                        mutants_table.add_row(k, emoji_by_status[status], key=k)
            else:
                assert event.data_table.id == 'mutants'
                # noinspection PyTypeChecker
                description_view: Static = self.query_one('#description')
                mutant_name = event.row_key.value
                self.loading_id = mutant_name
                path = self.path_by_name.get(mutant_name)
                source_file_mutation_data, stat = self.source_file_mutation_data_and_stat_by_path[str(path)]

                exit_code = source_file_mutation_data.exit_code_by_key[mutant_name]
                status = status_by_exit_code[exit_code]
                estimated_duration = source_file_mutation_data.estimated_time_of_tests_by_mutant.get(mutant_name, '?')
                duration = source_file_mutation_data.durations_by_key.get(mutant_name, '?')

                view_tests_description = f'(press t to view tests executed for this mutant)'

                match status:
                    case 'killed':
                        description = f'Killed ({exit_code=}): Mutant caused a test to fail 🎉'
                    case 'survived':
                        description = f'Survived ({exit_code=}): No test detected this mutant. {view_tests_description}'
                    case 'skipped':
                        description = f'Skipped ({exit_code=})'
                    case 'check was interrupted by user':
                        description = f'User interrupted ({exit_code=})'
                    case 'timeout':
                        description = (f'Timeout ({exit_code=}): Timed out because tests did not finish within {duration:.3f} seconds. '
                                            f'Tests without mutation took {estimated_duration:.3f} seconds. {view_tests_description}')
                    case 'no tests':
                        description = f'Untested ({exit_code=}): Skipped because selected tests do not execute this code.'
                    case 'segfault':
                        description = f'Segfault ({exit_code=}): Running pytest with this mutant segfaulted.'
                    case 'suspicious':
                        description = f'Unknown ({exit_code=}): Running pytest with this mutant resulted in an unknown exit code.'
                    case 'not checked':
                        description = 'Not checked in the last mutmut run.'
                    case _:
                        description = f'Unknown status ({exit_code=}, {status=})'
                description_view.update(f'\n {description}\n')

                diff_view: Static = self.query_one('#diff_view')
                diff_view.update('<loading code diff...>')

                def load_thread():
                    ensure_config_loaded()
                    try:
                        d = get_diff_for_mutant(event.row_key.value, path=path)
                        if event.row_key.value == self.loading_id:
                            diff_view.update(Syntax(d, "diff"))
                    except Exception as e:
                        diff_view.update(f"<{type(e)} {e}>")

                t = Thread(target=load_thread)
                t.start()

        def retest(self, pattern):
            self._run_subprocess_command('run', [pattern])

        def view_tests(self, mutant_name: str):
            self._run_subprocess_command('tests-for-mutant', [mutant_name])

        def _run_subprocess_command(self, command: str, args: list[str]):
            with self.suspend():
                browse_index = sys.argv.index('browse')
                initial_args = sys.argv[:browse_index]
                subprocess_args = [sys.executable, *initial_args, command, *args]
                print('>', *subprocess_args)
                subprocess.run(subprocess_args)
                input('press enter to return to browser')

            self.read_data()
            self.populate_files_table()

        def get_mutant_name_from_selection(self):
            # noinspection PyTypeChecker
            mutants_table: DataTable = self.query_one('#mutants')
            if mutants_table.cursor_row is None:
                return

            return mutants_table.get_row_at(mutants_table.cursor_row)[0]

        def action_retest_mutant(self):
            self.retest(self.get_mutant_name_from_selection())

        def action_retest_function(self):
            self.retest(self.get_mutant_name_from_selection().rpartition('__mutmut_')[0] + '__mutmut_*')

        def action_retest_module(self):
            self.retest(self.get_mutant_name_from_selection().rpartition('.')[0] + '.*')

        def action_apply_mutant(self):
            ensure_config_loaded()
            # noinspection PyTypeChecker
            mutants_table: DataTable = self.query_one('#mutants')
            if mutants_table.cursor_row is None:
                return
            apply_mutant(mutants_table.get_row_at(mutants_table.cursor_row)[0])

        def action_view_tests(self):
            self.view_tests(self.get_mutant_name_from_selection())

    ResultBrowser().run()


if __name__ == '__main__':
    cli()
