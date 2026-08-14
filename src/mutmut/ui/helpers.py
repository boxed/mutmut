"""Dependency-graph and cache-status helpers for the result browser.

These are pure functions (no Textual imports) so they can be unit-tested in
isolation from the UI. The dependency graph they operate on is
``state().function_dependencies``: a mapping of callee -> set of callers, keyed
by mangled names.
"""

from __future__ import annotations

from mutmut.models.cache_status import CacheStatus
from mutmut.utils.format_utils import mangled_name_from_mutant_name
from mutmut.utils.format_utils import raw_func_name_from_mangled


def expand_changed_functions(changed: set[str], deps: dict[str, set[str]]) -> set[str]:
    """Transitively expand changed functions to include all their callers.

    Walks backwards through the dependency graph: if ``baz`` changed and the
    chain is ``test -> foo -> bar -> baz``, returns ``{baz, bar, foo, test}``.

    Args:
        changed: Function names (any naming scheme) that changed directly.
        deps: Dependency graph mapping callee -> set of callers.

    Returns:
        The changed set plus every function that transitively depends on it.
    """
    result = set(changed)
    queue = list(changed)

    while queue:
        func = queue.pop()
        for caller in deps.get(func, set()):
            if caller not in result:
                result.add(caller)
                queue.append(caller)
    return result


def get_ordered_upstream_and_downstream_functions(
    raw_func_name: str, raw_deps: dict[str, set[str]], max_depth: int = 1
) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """Get the upstream (callers) and downstream (callees) of a function.

    Args:
        raw_func_name: The raw function name to expand around.
        raw_deps: Dependency graph (callee -> callers) keyed by raw names.
        max_depth: Maximum expansion depth (<= 0 means unlimited).

    Returns:
        ``(upstreams, downstreams)``, each a list of ``(name, depth)`` sorted by depth.
    """
    up_queue = [(raw_func_name, 0)]
    upstreams: dict[str, int] = {}

    while up_queue:
        func, depth = up_queue.pop()
        for caller in raw_deps.get(func, set()):
            if caller == raw_func_name:
                continue
            if caller not in upstreams:
                upstreams[caller] = depth + 1
                if max_depth <= 0 or depth + 1 < max_depth:
                    up_queue.append((caller, depth + 1))

    upstreams_sorted = sorted(upstreams.items(), key=lambda x: x[1])

    down_queue = [(raw_func_name, 0)]
    downstreams: dict[str, int] = {}

    while down_queue:
        func, depth = down_queue.pop()
        for callee, callers in raw_deps.items():
            if callee == raw_func_name:
                continue
            if func in callers and callee not in downstreams:
                downstreams[callee] = depth + 1
                if max_depth <= 0 or depth + 1 < max_depth:
                    down_queue.append((callee, depth + 1))

    downstreams_sorted = sorted(downstreams.items(), key=lambda x: x[1])

    return upstreams_sorted, downstreams_sorted


def _raw_deps_from(deps: dict[str, set[str]]) -> dict[str, set[str]]:
    """Convert a mangled callee->callers graph to raw (canonical) names."""
    raw_deps: dict[str, set[str]] = {}
    for callee, callers in deps.items():
        raw_callee = raw_func_name_from_mangled(callee)
        raw_deps.setdefault(raw_callee, set())
        for caller in callers:
            raw_deps[raw_callee].add(raw_func_name_from_mangled(caller))
    return raw_deps


def compute_funcs_with_invalid_deps(invalid_raw_funcs: set[str], deps: dict[str, set[str]]) -> set[str]:
    """Functions that transitively depend on an invalid function.

    Computed once at load time (rather than per-row) to keep the UI responsive.
    The invalid functions themselves are excluded from the result, so a tested
    mutant still shows CACHED even when a sibling mutant of the same function is
    untested.

    Args:
        invalid_raw_funcs: Raw names of functions with invalid mutants.
        deps: Original mangled callee -> callers graph.

    Returns:
        Raw names of functions that CALL (depend on) any invalid function.
    """
    if not invalid_raw_funcs or not deps:
        return set()

    raw_deps = _raw_deps_from(deps)
    all_affected = expand_changed_functions(invalid_raw_funcs, raw_deps)
    return all_affected - invalid_raw_funcs


def get_cache_status(
    mutant_name: str,
    exit_code: int | None,
    funcs_with_invalid_deps: set[str],
) -> CacheStatus:
    """Determine the cache status for a single mutant.

    Returns INVALID when untested (``exit_code is None``), STALE_DEPENDENCY when
    the function is unchanged but a dependency changed, else CACHED.
    """
    if exit_code is None:
        return CacheStatus.INVALID

    if not funcs_with_invalid_deps:
        return CacheStatus.CACHED

    raw_func_name = raw_func_name_from_mangled(mangled_name_from_mutant_name(mutant_name))

    if raw_func_name in funcs_with_invalid_deps:
        return CacheStatus.STALE_DEPENDENCY

    return CacheStatus.CACHED


def find_invalid_dependencies(
    raw_func_name: str,
    invalid_raw_funcs: set[str],
    deps: dict[str, set[str]],
) -> set[str]:
    """Which invalid functions ``raw_func_name`` transitively calls.

    Builds a caller -> callees graph from ``deps`` and walks forward, returning
    the reachable functions that are in ``invalid_raw_funcs``.
    """
    if not invalid_raw_funcs or not deps:
        return set()

    callees_by_caller: dict[str, set[str]] = {}
    for callee, callers in deps.items():
        raw_callee = raw_func_name_from_mangled(callee)
        for caller in callers:
            raw_caller = raw_func_name_from_mangled(caller)
            callees_by_caller.setdefault(raw_caller, set()).add(raw_callee)

    visited: set[str] = set()
    queue = [raw_func_name]
    invalid_deps: set[str] = set()

    while queue:
        func = queue.pop()
        if func in visited:
            continue
        visited.add(func)

        for callee in callees_by_caller.get(func, set()):
            if callee in invalid_raw_funcs:
                invalid_deps.add(callee)
            if callee not in visited:
                queue.append(callee)

    return invalid_deps
