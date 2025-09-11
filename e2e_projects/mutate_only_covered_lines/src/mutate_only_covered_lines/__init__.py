def hello_mutate_only_covered_lines(simple_branch: bool) -> str:
    if simple_branch:
        return "Hello from mutate_only_covered_lines! (true)"
    else:
        return "Hello from mutate_only_covered_lines! (false)"
