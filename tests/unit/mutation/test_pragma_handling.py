"""Tests for CST-based pragma comment parsing."""

import libcst as cst
import pytest
from libcst.metadata import MetadataWrapper

from mutmut.mutation.pragma_handling import PragmaParseError
from mutmut.mutation.pragma_handling import PragmaVisitor


def parse_pragmas(filename: str, source: str) -> tuple[set[int], set[int]]:
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module)
    visitor = PragmaVisitor(filename)
    wrapper.visit(visitor)
    return visitor.no_mutate_lines, visitor.ignore_node_lines


class TestParsePragmaLines:
    """Tests for PragmaVisitor basic pragma detection."""

    def test_no_pragmas(self):
        source = """
def foo():
    return 1 + 1
"""
        no_mutate, ignore_node_lines = parse_pragmas("test.py", source)
        assert no_mutate == set()
        assert ignore_node_lines == set()

    def test_simple_no_mutate(self):
        source = """
def foo():
    return 1 + 1  # pragma: no mutate
"""
        no_mutate, ignore_node_lines = parse_pragmas("test.py", source)
        assert no_mutate == {3}
        assert ignore_node_lines == set()

    def test_no_mutate_class(self):
        source = """
class Foo:  # pragma: no mutate block
    def method(self):
        return 1 + 1
"""
        no_mutate, ignore_node_lines = parse_pragmas("test.py", source)
        assert no_mutate == set()
        assert ignore_node_lines == {2, 3, 4}

    def test_no_mutate_function(self):
        source = """
def foo():  # pragma: no mutate block
    return 1 + 1
"""
        no_mutate, ignore_node_lines = parse_pragmas("test.py", source)
        assert no_mutate == set()
        assert ignore_node_lines == {2, 3}

    def test_mixed_pragmas(self):
        source = """
class Skipped:  # pragma: no mutate block
    def method(self):
        return 1 + 1

def skipped_func():  # pragma: no mutate block
    return 2 + 2

def mutated():
    return 3 + 3  # pragma: no mutate
"""
        no_mutate, ignore_node_lines = parse_pragmas("test.py", source)
        assert no_mutate == {10}
        assert ignore_node_lines == {2, 3, 4, 6, 7}

    def test_pragma_no_cover_with_no_mutate(self):
        source = """
def foo():
    return 1 + 1  # pragma: no cover, no mutate
"""
        no_mutate, ignore_node_lines = parse_pragmas("test.py", source)
        assert no_mutate == {3}
        assert ignore_node_lines == set()

    def test_single_line_function_body(self):
        """body is a SimpleStatementSuite."""
        source = """
def foo(): pass  # pragma: no mutate
"""
        no_mutate, ignore_node_lines = parse_pragmas("test.py", source)
        assert no_mutate == {2}
        assert ignore_node_lines == set()

    def test_single_line_if_body(self):
        source = """
if True: pass  # pragma: no mutate
"""
        no_mutate, ignore_node_lines = parse_pragmas("test.py", source)
        assert no_mutate == {2}
        assert ignore_node_lines == set()

    def test_other_pragma_ignored(self):
        source = """
def foo():
    return 1 + 1  # pragma: no cover
"""
        no_mutate, ignore_node_lines = parse_pragmas("test.py", source)
        assert no_mutate == set()
        assert ignore_node_lines == set()


class TestBlockPragma:
    """Tests for # pragma: no mutate block."""

    def test_own_line(self):
        source = """
if condition:
    # pragma: no mutate block
    x = 1
    y = 2
z = 3
"""
        no_mutate, _ = parse_pragmas("test.py", source)
        assert no_mutate == {3, 4, 5}

    def test_own_line_with_colon(self):
        source = """
if condition:
    # pragma: no mutate: block
    x = 1
    y = 2
z = 3
"""
        no_mutate, _ = parse_pragmas("test.py", source)
        assert no_mutate == {3, 4, 5}

    def test_inline(self):
        source = """
if condition:  # pragma: no mutate block
    x = 1
    y = 2
z = 3
"""
        no_mutate, ignore_node_lines = parse_pragmas("test.py", source)
        assert no_mutate == set()
        assert ignore_node_lines == {2, 3, 4}

    def test_does_not_affect_code_after_dedent(self):
        source = """
def foo():
    # pragma: no mutate block
    x = 1
    y = 2

def bar():
    z = 3
"""
        no_mutate, _ = parse_pragmas("test.py", source)
        assert no_mutate == {3, 4, 5}

    def test_does_not_affect_code_before_comment(self):
        source = """
def foo():
    x = 1
    # pragma: no mutate block
    y = 2
"""
        no_mutate, _ = parse_pragmas("test.py", source)
        assert no_mutate == {4, 5}

    def test_includes_nested_indentation(self):
        source = """
def foo():
    # pragma: no mutate block
    if True:
        x = 1
    y = 2
z = 3
"""
        no_mutate, _ = parse_pragmas("test.py", source)
        assert no_mutate == {3, 4, 5, 6}

    def test_inline_only_ignores_deeper(self):
        """Inline block pragma on an if-statement: the else branch at the same
        indentation is NOT ignored because it is not deeper."""
        source = """
if condition:  # pragma: no mutate block
    x = 1
    y = 2
else:
    z = 3
"""
        no_mutate, ignore_node_lines = parse_pragmas("test.py", source)
        assert no_mutate == set()
        assert ignore_node_lines == {2, 3, 4}

    def test_with_other_pragmas(self):
        source = """
class Skipped:  # pragma: no mutate block
    pass

def foo():
    # pragma: no mutate block
    x = 1
    y = 2

def bar():
    z = 3  # pragma: no mutate
"""
        no_mutate, ignore_node_lines = parse_pragmas("test.py", source)
        assert no_mutate == {6, 7, 8, 11}
        assert ignore_node_lines == {2, 3}

    def test_block_with_triple_quoted_string(self):
        """Triple-quoted strings with zero-indentation content must not
        break the block tracker -- this was the motivating bug for the
        CST-based rewrite."""
        source = """
def foo():
    # pragma: no mutate block
    x = \"""
this line has zero indentation
""\"
    y = 2
"""
        no_mutate, _ = parse_pragmas("test.py", source)
        assert no_mutate == {3, 4, 5, 6, 7}


class TestSelectionPragma:
    """Tests for # pragma: no mutate start / end pairs."""

    def test_start_end_ignores_enclosed_lines(self):
        source = """
x = 1
# pragma: no mutate start
y = 2
z = 3
# pragma: no mutate end
w = 4
"""
        no_mutate, _ = parse_pragmas("test.py", source)
        assert no_mutate == {3, 4, 5, 6}

    def test_start_end_includes_blank_lines(self):
        source = """
# pragma: no mutate start
x = 1

y = 2
# pragma: no mutate end
z = 3
"""
        no_mutate, _ = parse_pragmas("test.py", source)
        assert no_mutate == {2, 3, 4, 5, 6}

    def test_start_end_ignores_indentation(self):
        """Selection mode ignores all lines regardless of indent level."""
        source = """
def foo():
    # pragma: no mutate start
    x = 1
    if True:
        y = 2
    # pragma: no mutate end
    z = 3
"""
        no_mutate, _ = parse_pragmas("test.py", source)
        assert no_mutate == {3, 4, 5, 6, 7}

    def test_end_without_start_raises(self):
        source = """
x = 1
# pragma: no mutate end
"""
        with pytest.raises(PragmaParseError, match="without a # pragma: no mutate start"):
            parse_pragmas("test.py", source)

    def test_end_without_start_includes_filename(self):
        source = """
x = 1
# pragma: no mutate end
"""
        with pytest.raises(PragmaParseError, match="my_module.py:3"):
            parse_pragmas("my_module.py", source)

    def test_start_end_with_other_pragmas(self):
        source = """
a = 1  # pragma: no mutate
# pragma: no mutate start
b = 2
c = 3
# pragma: no mutate end
d = 4
"""
        no_mutate, _ = parse_pragmas("test.py", source)
        assert no_mutate == {2, 3, 4, 5, 6}


class TestNestedContextErrors:
    """Opening a new no-mutate context inside an existing one raises PragmaParseError."""

    def test_block_inside_block_raises(self):
        source = """
def foo():
    # pragma: no mutate block
    # pragma: no mutate block
    x = 1
"""
        with pytest.raises(PragmaParseError, match="test.py:3"):
            parse_pragmas("test.py", source)

    def test_start_inside_block_raises(self):
        source = """
def foo():
    # pragma: no mutate block
    # pragma: no mutate start
    x = 1
    # pragma: no mutate end
"""
        with pytest.raises(PragmaParseError, match="test.py:3"):
            parse_pragmas("test.py", source)

    def test_block_inside_selection_raises(self):
        source = """
# pragma: no mutate start
# pragma: no mutate block
x = 1
# pragma: no mutate end
"""
        with pytest.raises(PragmaParseError, match="test.py:2"):
            parse_pragmas("test.py", source)

    def test_start_inside_selection_raises(self):
        source = """
# pragma: no mutate start
# pragma: no mutate start
x = 1
# pragma: no mutate end
"""
        with pytest.raises(PragmaParseError, match="test.py:2"):
            parse_pragmas("test.py", source)

    def test_error_includes_filename_and_original_context(self):
        source = """
def foo():
    # pragma: no mutate block
    # pragma: no mutate block
    pass
"""
        with pytest.raises(PragmaParseError) as exc_info:
            parse_pragmas("my_module.py", source)
        assert "my_module.py:3" in str(exc_info.value)
        assert "my_module.py:4" in str(exc_info.value)

    def test_unclosed_selection_raises(self):
        source = """
x = 1
# pragma: no mutate start
y = 2
"""
        with pytest.raises(PragmaParseError, match="Missing no mutate end"):
            parse_pragmas("test.py", source)
