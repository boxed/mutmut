from mutmut.import_hook import MutateFinder
import sys


def mutator_hook(path):
    if path == MutateFinder.file_to_mutate.rsplit('/', 1)[0] == path:
        return MutateFinder(path)
    raise ImportError

sys.path_hooks.append(mutator_hook)
sys.path_importer_cache.clear()


def pytest_addoption(parser):
    group = parser.getgroup("mutation testing")
    group._addoption(
        '--mutate',
        dest="mutate",
        help="run specified mutation on specified file. Format is: /full/path/to/file.py:MUTATION_NUMBER (mutation number is 0 indexed)")


def pytest_configure(config):
    m = config.getvalue("mutate")
    if m:
        MutateFinder.file_to_mutate, MutateFinder.mutation_number = m.split(':')
        MutateFinder.mutation_number = int(MutateFinder.mutation_number)
        assert MutateFinder.mutation_number >= 0
