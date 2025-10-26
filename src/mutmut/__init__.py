import importlib.metadata
from collections import defaultdict

__version__ = importlib.metadata.version("mutmut")


duration_by_test = defaultdict(float)
stats_time = None
config = None

_stats = set()
tests_by_mangled_function_name = defaultdict(set)
_covered_lines = None

def _reset_globals():
    global duration_by_test, stats_time, config, _stats, tests_by_mangled_function_name
    global _covered_lines

    duration_by_test.clear()
    stats_time = None
    config = None
    _stats = set()
    tests_by_mangled_function_name = defaultdict(set)
    _covered_lines = None
