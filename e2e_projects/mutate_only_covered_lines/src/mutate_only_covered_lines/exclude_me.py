"""Code that coverage.py is told not to measure.

Every excluded region below is *executed* by the tests, so it ends up in the covered
lines. Only coverage.py's exclusion rules can keep it from being mutated.
"""

debug_only = True


def excluded_function(a: int, b: int) -> int:  # pragma: no cover
    result = (
        a
        + b
    )
    return result


def excluded_branch(flag: bool) -> int:
    if flag:  # pragma: no cover
        return 1 + 1
    return 2 + 2


def excluded_by_coverage_config(a: int, b: int) -> int:
    total = a * b
    if debug_only:
        total = (
            total
            + 1
        )
    return total


def excluded_case(kind: str) -> int:
    # dropping a case is a mutation of the `match`, not of the excluded lines themselves
    match kind:
        case "a":
            return 1
        case "b":
            return 2
        case _NEVER:
            raise Exception("Can't happen")
