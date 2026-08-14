"""Tests for the browser dependency/cache-status helpers."""

from mutmut.models.cache_status import CacheStatus
from mutmut.ui.helpers import compute_funcs_with_invalid_deps
from mutmut.ui.helpers import expand_changed_functions
from mutmut.ui.helpers import find_invalid_dependencies
from mutmut.ui.helpers import get_cache_status
from mutmut.ui.helpers import get_ordered_upstream_and_downstream_functions

# Call chain test -> a -> b -> c, expressed as callee -> callers (mangled names).
MANGLED_DEPS = {
    "m.x_c": {"m.x_b"},
    "m.x_b": {"m.x_a"},
}
# Same graph with raw names.
RAW_DEPS = {
    "m.c": {"m.b"},
    "m.b": {"m.a"},
}


class TestExpandChangedFunctions:
    def test_walks_callers_transitively(self):
        assert expand_changed_functions({"m.c"}, RAW_DEPS) == {"m.c", "m.b", "m.a"}

    def test_leaf_change_only_itself(self):
        assert expand_changed_functions({"m.a"}, RAW_DEPS) == {"m.a"}

    def test_empty(self):
        assert expand_changed_functions(set(), RAW_DEPS) == set()


class TestComputeFuncsWithInvalidDeps:
    def test_excludes_the_invalid_function_itself(self):
        result = compute_funcs_with_invalid_deps({"m.c"}, MANGLED_DEPS)
        assert result == {"m.b", "m.a"}

    def test_empty_inputs(self):
        assert compute_funcs_with_invalid_deps(set(), MANGLED_DEPS) == set()
        assert compute_funcs_with_invalid_deps({"m.c"}, {}) == set()


class TestGetCacheStatus:
    def test_untested_is_invalid(self):
        assert get_cache_status("m.x_c__mutmut_1", None, set()) == CacheStatus.INVALID

    def test_no_invalid_deps_is_cached(self):
        assert get_cache_status("m.x_b__mutmut_1", 0, set()) == CacheStatus.CACHED

    def test_function_with_invalid_dep_is_stale(self):
        assert get_cache_status("m.x_b__mutmut_1", 0, {"m.b", "m.a"}) == CacheStatus.STALE_DEPENDENCY

    def test_function_not_in_invalid_deps_is_cached(self):
        assert get_cache_status("m.x_z__mutmut_1", 0, {"m.b", "m.a"}) == CacheStatus.CACHED


class TestFindInvalidDependencies:
    def test_forward_walk_finds_invalid_callee(self):
        assert find_invalid_dependencies("m.a", {"m.c"}, MANGLED_DEPS) == {"m.c"}

    def test_no_invalid_deps_when_none_reachable(self):
        assert find_invalid_dependencies("m.c", {"m.c"}, MANGLED_DEPS) == set()

    def test_empty_inputs(self):
        assert find_invalid_dependencies("m.a", set(), MANGLED_DEPS) == set()


class TestUpstreamDownstream:
    def test_one_level(self):
        up, down = get_ordered_upstream_and_downstream_functions("m.b", RAW_DEPS, max_depth=1)
        assert up == [("m.a", 1)]
        assert down == [("m.c", 1)]

    def test_full_depth_expands_transitively(self):
        up, down = get_ordered_upstream_and_downstream_functions("m.b", RAW_DEPS, max_depth=0)
        # b's only caller is a (upstream); b's only callee is c (downstream).
        assert up == [("m.a", 1)]
        assert down == [("m.c", 1)]

    def test_middle_of_longer_chain(self):
        # test -> a -> b -> c -> d : from c, upstream = b,a ; downstream = d
        raw = {"m.b": {"m.a"}, "m.c": {"m.b"}, "m.d": {"m.c"}}
        up, down = get_ordered_upstream_and_downstream_functions("m.c", raw, max_depth=0)
        assert up == [("m.b", 1), ("m.a", 2)]
        assert down == [("m.d", 1)]


class TestCacheStatusOrdering:
    def test_severity_ordering(self):
        assert CacheStatus.CACHED < CacheStatus.STALE_DEPENDENCY < CacheStatus.INVALID

    def test_worst(self):
        assert CacheStatus.CACHED.worst(CacheStatus.INVALID) == CacheStatus.INVALID
        assert CacheStatus.STALE_DEPENDENCY.worst(CacheStatus.CACHED) == CacheStatus.STALE_DEPENDENCY
        assert CacheStatus.INVALID.worst(CacheStatus.STALE_DEPENDENCY) == CacheStatus.INVALID
