from mutmut.models.cache_status import CacheStatus
from mutmut.utils.format_utils import mangled_name_from_mutant_name
from mutmut.utils.format_utils import raw_func_name_from_mangled


def expand_changed_functions(changed: set[str], deps: dict[str, set[str]]) -> set[str]:
    """Transitively expand changed functions to include all callers.

    Given a set of directly changed functions, walks backwards through the
    dependency graph to find all functions that transitively depend on them.

    Example: If baz() changed and the call chain is test -> foo -> bar -> baz,
    this returns {'baz', 'bar', 'foo', 'test'} (all functions whose behavior
    depends on baz).

    Args:
        changed: Set of function names (mangled) that have directly changed
        deps: Dependency graph mapping callee -> set of callers

    Returns:
        Expanded set including all callers that transitively depend on changed functions
            (including the originally changed functions).
    """
    result = set(changed)
    queue = list(changed)

    while queue:
        func = queue.pop()
        callers = deps.get(func, set())
        for caller in callers:
            if caller not in result:
                result.add(caller)
                queue.append(caller)
    return result


def get_ordered_upstream_and_downstream_functions(
    raw_func_name: str, raw_deps: dict[str, set[str]], max_depth: int = 1
) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """Get the upstream and downstream functions for a given function.

    Args:
        raw_func_name: The raw function name to get the upstream and downstream functions for
        raw_deps: The dependency graph
        max_depth: The maximum depth to expand the upstream and downstream functions (0/negative for no limit)

    Returns:
        A tuple of two lists of tuples, the first list is the upstream functions and the second list is the downstream functions
    """
    up_queue = [(raw_func_name, 0)]
    upstreams: dict[str, int] = {}

    while up_queue:
        func, depth = up_queue.pop()
        callers = raw_deps.get(func, set())
        for caller in callers:
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


def compute_funcs_with_invalid_deps(invalid_raw_funcs: set[str], deps: dict[str, set[str]]) -> set[str]:
    """Computes all functions that transitively depend on invalid functions.

    Uses the original callee->callers graph to find all callers of invalid functions.
    This is done once at load time to avoid expensive BFS per-row which would make
    the UI feel sluggish if done lazily.

    Note: This returns only the CALLERS of invalid functions, not the invalid
    functions themselves. This ensures that a tested mutant shows as CACHED
    even if other mutants of the same function are untested.

    Args:
        invalid_raw_funcs: Set of raw function names that have invalid mutants
        deps: Original dependency graph (callee -> set of callers), using mangled names

    Returns:
        Set of raw function names that CALL (depend on) any invalid function
    """
    if not invalid_raw_funcs or not deps:
        return set()

    raw_deps: dict[str, set[str]] = {}
    for callee, callers in deps.items():
        raw_callee = raw_func_name_from_mangled(callee)
        if raw_callee not in raw_deps:
            raw_deps[raw_callee] = set()
        for caller in callers:
            raw_deps[raw_callee].add(raw_func_name_from_mangled(caller))

    all_affected = expand_changed_functions(invalid_raw_funcs, raw_deps)
    return all_affected - invalid_raw_funcs


def get_cache_status(
    mutant_name: str,
    exit_code: int | None,
    funcs_with_invalid_deps: set[str],
) -> CacheStatus:
    """Determine validity status indicator for a mutant.

    Args:
        mutant_name: The mutant name (e.g., "module.x_func__mutmut_1")
        exit_code: The exit code for this mutant (None if not tested)
        funcs_with_invalid_deps: Pre-computed set of functions with invalid dependencies

    Returns:
        CacheStatus.CACHED - valid result (tested and no changed dependencies)
        CacheStatus.STALE_DEPENDENCY - function is unchanged but a dependency changed
        CacheStatus.INVALID - function itself needs retest (exit_code is None)
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
    """Find which invalid functions a given function transitively depends on.

    Builds a callees graph (caller -> callees) from the deps graph and walks
    forward to find all callees, returning those that are in invalid_raw_funcs.

    Args:
        raw_func_name: The raw function name to check dependencies for
        invalid_raw_funcs: Set of raw function names that have invalid mutants
        deps: Original dependency graph (callee -> set of callers), using mangled names

    Returns:
        Set of raw function names that are invalid AND are dependencies of raw_func_name
    """
    if not invalid_raw_funcs or not deps:
        return set()

    callees_by_caller: dict[str, set[str]] = {}
    for callee, callers in deps.items():
        raw_callee = raw_func_name_from_mangled(callee)
        for caller in callers:
            raw_caller = raw_func_name_from_mangled(caller)
            if raw_caller not in callees_by_caller:
                callees_by_caller[raw_caller] = set()
            callees_by_caller[raw_caller].add(raw_callee)

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
