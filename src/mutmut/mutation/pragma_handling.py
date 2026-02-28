"""Pragma comment parsing for mutation control."""


def parse_pragma_lines(source: str) -> tuple[set[int], set[int], set[int]]:
    """Parse all pragma: no mutate variants.

    Each set is mutually exclusive.

    Supported pragmas:
        - ``# pragma: no mutate`` - skip this line only
        - ``# pragma: no mutate class`` - skip entire class
        - ``# pragma: no mutate: class`` - skip entire class (alternative syntax)
        - ``# pragma: no mutate function`` - skip entire function
        - ``# pragma: no mutate: function`` - skip entire function (alternative syntax)

    :return: A tuple of (no_mutate_lines, class_lines, function_lines)
    """
    no_mutate_lines: set[int] = set()
    class_lines: set[int] = set()
    function_lines: set[int] = set()

    for i, line in enumerate(source.split("\n")):
        if "# pragma:" not in line:
            continue

        pragma_content = line.partition("# pragma:")[-1]
        line_num = i + 1

        if "no mutate" not in pragma_content:
            continue

        # Check for specific variants first (more specific matches)
        if "no mutate class" in pragma_content or "no mutate: class" in pragma_content:
            class_lines.add(line_num)
        elif "no mutate function" in pragma_content or "no mutate: function" in pragma_content:
            function_lines.add(line_num)
        else:
            # Generic "no mutate" (not class or function)
            no_mutate_lines.add(line_num)

    return no_mutate_lines, class_lines, function_lines
