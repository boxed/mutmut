def hello_mutate_only_covered_lines(simple_branch: bool) -> str:
    if simple_branch:
        return "Hello from mutate_only_covered_lines! (true)"
    else:
        return "Hello from mutate_only_covered_lines! (false)"

def function_with_pragma() -> int:
    return 1 # pragma: no mutate

def mutate_only_covered_lines_multiline(simple_branch: bool) -> str:
    x = (
        "Foo"
        "Bar" # coverage.py incorrectly reports this line as not covered. If that changes, tests will break
    )
    n = 1 \
        + 2
    # should mutate keys and values
    d = {
        'a': 1,
        'b': 2,
    }
    # should mutate function call parameters
    e = dict(
        a=1,
        b=2,
    )
    if simple_branch:
        y = [
            i * 2
            for i in range(10)
            if i % 2 == 0
        ]
        return f"Hello from mutate_only_covered_lines!" \
            f" (true) {x} {y}"
    else:
        y = [
            i * 2
            for i in range(10)
            if i % 2 == 0
        ]
        return f"Hello from mutate_only_covered_lines!" \
            f" (false) {x} {y}"

