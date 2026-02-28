"""Tests for strings.py module."""

from benchmark import strings


class TestStrings:
    """Test string-heavy functions."""

    def test_messages_batch_1(self):
        """Test message strings."""
        result = strings.messages_batch_1()
        assert result == ("hello", "world")

    def test_labels_batch_1(self):
        """Test label strings."""
        result = strings.labels_batch_1()
        assert result[0] == "name"

    def test_states(self):
        """Test state strings."""
        result = strings.states()
        assert result == ("pending", "active")

    def test_format_name(self):
        """Test f-string with name."""
        assert strings.format_name("Alice") == "Name: Alice"

    def test_format_count(self):
        """Test f-string with count."""
        assert strings.format_count(42) == "Count: 42"

    def test_format_result(self):
        """Test f-string with result."""
        assert strings.format_result(10, "kg") == "Result: 10 kg"

    def test_case_methods_1(self):
        """Test case methods."""
        lower, upper = strings.case_methods_1("HeLLo")
        assert lower == "hello"
        assert upper == "HELLO"

    def test_strip_methods_1(self):
        """Test strip methods."""
        left, right = strings.strip_methods_1("  hello  ")
        assert left == "hello  "
        assert right == "  hello"

    def test_find_methods_1(self):
        """Test find methods."""
        pos1, pos2 = strings.find_methods_1("hello world hello", "hello")
        assert pos1 == 0
        assert pos2 == 12

    def test_split_methods_1(self):
        """Test split methods."""
        parts1, parts2 = strings.split_methods_1("a-b-c-d", "-")
        assert parts1 == ["a", "b", "c-d"]
        assert parts2 == ["a-b", "c", "d"]

    def test_partition_methods(self):
        """Test partition methods."""
        p1, p2 = strings.partition_methods("hello-world", "-")
        assert p1 == ("hello", "-", "world")
        assert p2 == ("hello", "-", "world")

    def test_messages_batch_2(self):
        """Test batch 2 strings."""
        result = strings.messages_batch_2()
        assert result == ("start", "stop", "pause")

    def test_messages_batch_3(self):
        """Test batch 3 strings."""
        result = strings.messages_batch_3()
        assert result[0] == "error"

    def test_symbols(self):
        """Test symbol strings."""
        result = strings.symbols()
        assert result == ("alpha", "beta", "gamma")

    def test_keywords(self):
        """Test keyword strings."""
        result = strings.keywords()
        assert "true" in result

    def test_format_error(self):
        """Test error f-string."""
        assert strings.format_error(404, "Not Found") == "Error 404: Not Found"

    def test_format_coords(self):
        """Test coords f-string."""
        assert strings.format_coords(1, 2) == "(1, 2)"

    def test_format_path(self):
        """Test path f-string."""
        assert strings.format_path("/home", "file.txt") == "/home/file.txt"

    def test_format_greeting(self):
        """Test greeting f-string."""
        assert strings.format_greeting("Dr", "Smith") == "Hello, Dr Smith!"

    def test_case_methods_2(self):
        """Test more case methods."""
        title, cap, swap = strings.case_methods_2("hELLO")
        assert title == "Hello"
        assert cap == "Hello"

    def test_strip_methods_2(self):
        """Test strip with chars."""
        left, right, both = strings.strip_methods_2("xxhelloxx", "x")
        assert left == "helloxx"
        assert right == "xxhello"
        assert both == "hello"

    def test_find_methods_2(self):
        """Test find with start."""
        pos1, pos2 = strings.find_methods_2("hello world hello", "hello", 1)
        assert pos1 == 12

    def test_replace_methods(self):
        """Test replace methods."""
        r1, r2 = strings.replace_methods("a-b-c", "-", "_")
        assert r1 == "a_b_c"
        assert r2 == "a_b-c"

    def test_justify_methods(self):
        """Test justify methods."""
        left, right, center = strings.justify_methods("hi", 5)
        assert len(left) == 5
        assert len(right) == 5

    def test_index_methods(self):
        """Test index methods."""
        i1, i2 = strings.index_methods("hello world hello", "hello")
        assert i1 == 0
        assert i2 == 12

    def test_prefix_suffix_methods(self):
        """Test prefix/suffix removal."""
        r1, r2 = strings.prefix_suffix_methods("pre_test_suf")
        assert r1 == "test_suf"
        assert r2 == "pre_test"
