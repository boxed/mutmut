from collections import defaultdict

__version__ = '3.3.0'


duration_by_test = {}
stats_time = None
config = None

_stats = set()
tests_by_mangled_function_name = defaultdict(set)


def _reset_globals():
    global duration_by_test, stats_time, config, _stats, tests_by_mangled_function_name

    duration_by_test = {}
    stats_time = None
    config = None
    _stats = set()
    tests_by_mangled_function_name = defaultdict(set)
