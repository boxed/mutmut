"""Tests for arguments.py module."""

from benchmark import arguments


class TestArguments:
    """Test argument functions."""

    def test_combiner(self):
        """Test combiner function."""
        # Normal case - both values provided
        assert arguments.combiner("a", "b") == "a-b"
        # First is None - should return None
        assert arguments.combiner(None, "b") is None
        # Second is None - should return None
        assert arguments.combiner("a", None) is None
        # Both None - should return None
        assert arguments.combiner(None, None) is None

    def test_helper_2(self):
        """Test helper_2."""
        assert arguments.helper_2(1, 2) == (1, 2)

    def test_helper_3(self):
        """Test helper_3."""
        assert arguments.helper_3(1, 2, 3) == (1, 2, 3)

    def test_call_2args_batch_1(self):
        """Test 2-arg calls."""
        result = arguments.call_2args_batch_1()
        assert result[0] == (1, 2)

    def test_call_3args_batch_1(self):
        """Test 3-arg calls."""
        result = arguments.call_3args_batch_1()
        assert result[0] == (1, 2, 3)

    def test_dict_2keys_batch_1(self):
        """Test dict with 2 keys."""
        result = arguments.dict_2keys_batch_1()
        assert result[0] == {"a": 1, "b": 2}

    def test_dict_3keys_batch_1(self):
        """Test dict with 3 keys."""
        result = arguments.dict_3keys_batch_1()
        assert result[0] == {"x": 1, "y": 2, "z": 3}

    def test_string_method_calls(self):
        """Test string method calls."""
        result = arguments.string_method_calls()
        assert result[0] == ["a", "b", "c-d-e"]

    def test_format_calls(self):
        """Test format calls."""
        result = arguments.format_calls()
        assert result[0] == "hello world"
