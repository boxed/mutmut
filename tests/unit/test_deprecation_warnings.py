"""Tests for deprecated global access warnings."""

import warnings

import pytest

from mutmut.configuration import config as configuration_config


class TestDeprecatedGlobalAccess:
    """Tests for deprecated mutmut.<global> access patterns."""

    def test_stats_time_access_emits_warning(self):
        """Accessing mutmut.stats_time should emit FutureWarning."""
        import mutmut

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = mutmut.stats_time

            assert len(w) == 1
            assert issubclass(w[0].category, FutureWarning)
            assert "stats_time" in str(w[0].message)
            assert "deprecated" in str(w[0].message).lower()

    def test_duration_by_test_access_emits_warning(self):
        """Accessing mutmut.duration_by_test should emit FutureWarning."""
        import mutmut

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = mutmut.duration_by_test

            assert len(w) == 1
            assert issubclass(w[0].category, FutureWarning)
            assert "duration_by_test" in str(w[0].message)

    def test_tests_by_mangled_function_name_access_emits_warning(self):
        """Accessing mutmut.tests_by_mangled_function_name should emit FutureWarning."""
        import mutmut

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = mutmut.tests_by_mangled_function_name

            assert len(w) == 1
            assert issubclass(w[0].category, FutureWarning)
            assert "tests_by_mangled_function_name" in str(w[0].message)

    def test_stats_access_emits_warning(self):
        """Accessing mutmut._stats should emit FutureWarning."""
        import mutmut

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = mutmut._stats

            assert len(w) == 1
            assert issubclass(w[0].category, FutureWarning)
            assert "_stats" in str(w[0].message)

    def test_covered_lines_access_emits_warning(self):
        """Accessing mutmut._covered_lines should emit FutureWarning."""
        import mutmut

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = mutmut._covered_lines

            assert len(w) == 1
            assert issubclass(w[0].category, FutureWarning)
            assert "_covered_lines" in str(w[0].message)

    def test_deprecated_access_returns_state_value(self):
        """Deprecated access should return the value from state()."""
        import mutmut
        from mutmut.state import state

        # Set a value via state()
        state().stats_time = 42.0

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            # Access via deprecated path should return same value
            assert mutmut.stats_time == 42.0

    def test_config_access_still_works(self):
        """Accessing mutmut.config should still emit warning and work."""
        import mutmut

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = mutmut.config

            assert len(w) == 1
            assert issubclass(w[0].category, FutureWarning)
            assert "config" in str(w[0].message)
            assert config is configuration_config()

    def test_unknown_attribute_raises_attribute_error(self):
        """Accessing unknown attribute should raise AttributeError."""
        import mutmut

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = mutmut.nonexistent_attribute
