"""Tests for pragma comment parsing."""

from mutmut.mutation.pragma_handling import parse_pragma_lines


class TestParsePragmaLines:
    """Tests for parse_pragma_lines function."""

    def test_no_pragmas(self):
        source = """def foo():
    return 1 + 1
"""
        no_mutate, class_lines, function_lines = parse_pragma_lines(source)
        assert no_mutate == set()
        assert class_lines == set()
        assert function_lines == set()

    def test_simple_no_mutate(self):
        source = """def foo():
    return 1 + 1  # pragma: no mutate
"""
        no_mutate, class_lines, function_lines = parse_pragma_lines(source)
        assert no_mutate == {2}
        assert class_lines == set()
        assert function_lines == set()

    def test_no_mutate_class(self):
        source = """class Foo:  # pragma: no mutate class
    def method(self):
        return 1 + 1
"""
        no_mutate, class_lines, function_lines = parse_pragma_lines(source)
        assert no_mutate == set()
        assert class_lines == {1}
        assert function_lines == set()

    def test_no_mutate_class_with_colon(self):
        source = """class Foo:  # pragma: no mutate: class
    def method(self):
        return 1 + 1
"""
        no_mutate, class_lines, function_lines = parse_pragma_lines(source)
        assert no_mutate == set()
        assert class_lines == {1}
        assert function_lines == set()

    def test_no_mutate_function(self):
        source = """def foo():  # pragma: no mutate function
    return 1 + 1
"""
        no_mutate, class_lines, function_lines = parse_pragma_lines(source)
        assert no_mutate == set()
        assert class_lines == set()
        assert function_lines == {1}

    def test_no_mutate_function_with_colon(self):
        source = """def foo():  # pragma: no mutate: function
    return 1 + 1
"""
        no_mutate, class_lines, function_lines = parse_pragma_lines(source)
        assert no_mutate == set()
        assert class_lines == set()
        assert function_lines == {1}

    def test_mixed_pragmas(self):
        source = """class Skipped:  # pragma: no mutate class
    def method(self):
        return 1 + 1

def skipped_func():  # pragma: no mutate function
    return 2 + 2

def mutated():
    return 3 + 3  # pragma: no mutate
"""
        no_mutate, class_lines, function_lines = parse_pragma_lines(source)
        assert no_mutate == {9}
        assert class_lines == {1}
        assert function_lines == {5}

    def test_pragma_no_cover_with_no_mutate(self):
        source = """def foo():
    return 1 + 1  # pragma: no cover, no mutate
"""
        no_mutate, class_lines, function_lines = parse_pragma_lines(source)
        assert no_mutate == {2}
        assert class_lines == set()
        assert function_lines == set()

    def test_other_pragma_ignored(self):
        source = """def foo():
    return 1 + 1  # pragma: no cover
"""
        no_mutate, class_lines, function_lines = parse_pragma_lines(source)
        assert no_mutate == set()
        assert class_lines == set()
        assert function_lines == set()
