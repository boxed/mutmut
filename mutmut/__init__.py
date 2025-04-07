from collections import defaultdict

__version__ = '3.2.3'


duration_by_test = {}
stats_time = None
config = None

_stats = set()
tests_by_mangled_function_name = defaultdict(set)
