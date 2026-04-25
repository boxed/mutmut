from pathlib import Path

import pytest

from mutmut.configuration import Config
from mutmut.configuration import _config_reader
from mutmut.configuration import _guess_source_paths
from mutmut.configuration import _load_config


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config singleton before and after each test."""
    Config.reset()
    yield
    Config.reset()


@pytest.fixture
def in_tmp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Change to a temporary directory for the duration of the test."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestConfigSingleton:
    def test_get_loads_config(self, in_tmp_dir: Path):
        (in_tmp_dir / "src").mkdir()
        config = Config.get()
        assert config is not None
        assert isinstance(config, Config)

    def test_get_returns_same_instance(self, in_tmp_dir: Path):
        (in_tmp_dir / "src").mkdir()
        config1 = Config.get()
        config2 = Config.get()
        assert config1 is config2

    def test_reset_clears_singleton(self, in_tmp_dir: Path):
        (in_tmp_dir / "src").mkdir()
        config1 = Config.get()
        Config.reset()
        config2 = Config.get()
        assert config1 is not config2

    def test_ensure_loaded_is_idempotent(self, in_tmp_dir: Path):
        (in_tmp_dir / "src").mkdir()
        Config.ensure_loaded()
        config1 = Config.get()
        Config.ensure_loaded()
        config2 = Config.get()
        assert config1 is config2


class TestShouldMutateFile:
    @staticmethod
    def _get_config(only_mutate: list[str], do_not_mutate: list[str]) -> Config:
        # only the "only_mutate" and "do_not_mutate" configs are important for these tests
        return Config(
            only_mutate=only_mutate,
            do_not_mutate=do_not_mutate,
            also_copy=[],
            max_stack_depth=-1,
            debug=False,
            source_paths=[],
            pytest_add_cli_args=[],
            pytest_add_cli_args_test_selection=[],
            mutate_only_covered_lines=False,
            timeout_multiplier=15.0,
            timeout_constant=1.0,
            type_check_command=[],
            use_setproctitle=False,
        )

    def test_ignores_non_python_files(self):
        config = self._get_config(
            only_mutate=[],
            do_not_mutate=[],
        )
        assert config.should_mutate("foo.txt") is False
        assert config.should_mutate("foo.js") is False
        assert config.should_mutate("foo") is False

    def test_includes_python_files(self):
        config = self._get_config(
            only_mutate=[],
            do_not_mutate=[],
        )
        assert config.should_mutate("foo.py") is True
        assert config.should_mutate("src/foo.py") is True

    def test_respects_do_not_mutate_exact_match(self):
        config = self._get_config(
            only_mutate=[],
            do_not_mutate=["foo.py"],
        )
        assert config.should_mutate("foo.py") is False
        assert config.should_mutate("bar.py") is True

    def test_respects_do_not_mutate_glob_pattern(self):
        config = self._get_config(
            only_mutate=[],
            do_not_mutate=["**/test_*.py", "src/ignore_*.py"],
        )
        assert config.should_mutate("tests/test_foo.py") is False
        assert config.should_mutate("src/ignore_me.py") is False
        assert config.should_mutate("src/keep_me.py") is True

    def test_respects_only_mutate(self):
        config = self._get_config(
            # without a glob, the `src/` is pointless
            only_mutate=["src/", "foo/*"],
            do_not_mutate=[],
        )
        assert config.should_mutate("tests/test_foo.py") is False
        assert config.should_mutate("src/main.py") is False
        assert config.should_mutate("foo/main.py") is True
        assert config.should_mutate("foo/nested/main.py") is True

    def test_respects_only_mutate_with_do_not_mutate(self):
        config = self._get_config(
            only_mutate=["src/api/*"],
            do_not_mutate=["src/api/models/*"],
        )
        # matched by only_mutate
        assert config.should_mutate("src/api/endpoints/user.py") is True
        # matched by only_mutate but excluded by do_not_mutate
        assert config.should_mutate("src/api/models/user.py") is False
        # not matched by only_mutate
        assert config.should_mutate("src/services/user.py") is False

    def test_accepts_path_objects(self):
        config = self._get_config(
            only_mutate=[],
            do_not_mutate=["foo.py"],
        )
        assert config.should_mutate(Path("foo.py")) is False
        assert config.should_mutate(Path("bar.py")) is True


class TestConfigReaderPyprojectToml:
    def test_reads_from_pyproject_toml(self, in_tmp_dir: Path):
        (in_tmp_dir / "pyproject.toml").write_text("""
[tool.mutmut]
debug = true
max_stack_depth = 10
source_paths = ["src", "lib"]
do_not_mutate = ["**/migrations/*"]
""")
        reader = _config_reader()
        assert reader("debug", False) is True
        assert reader("max_stack_depth", -1) == 10
        assert reader("source_paths", []) == ["src", "lib"]
        assert reader("do_not_mutate", []) == ["**/migrations/*"]

    def test_returns_default_for_missing_key(self, in_tmp_dir: Path):
        (in_tmp_dir / "pyproject.toml").write_text("""
[tool.mutmut]
debug = true
""")
        reader = _config_reader()
        assert reader("nonexistent", "default_value") == "default_value"
        assert reader("max_stack_depth", -1) == -1

    def test_handles_missing_mutmut_section(self, in_tmp_dir: Path):
        (in_tmp_dir / "pyproject.toml").write_text("""
[tool.other]
foo = "bar"
""")
        # Should fall through to setup.cfg reader
        reader = _config_reader()
        assert reader("debug", False) is False


class TestConfigReaderSetupCfg:
    def test_reads_from_setup_cfg(self, in_tmp_dir: Path):
        (in_tmp_dir / "setup.cfg").write_text("""
[mutmut]
debug = true
max_stack_depth = 5
source_paths = src
""")
        reader = _config_reader()
        assert reader("debug", False) is True
        assert reader("max_stack_depth", -1) == 5
        assert reader("source_paths", []) == ["src"]

    def test_parses_multiline_list(self, in_tmp_dir: Path):
        (in_tmp_dir / "setup.cfg").write_text("""
[mutmut]
do_not_mutate =
    **/migrations/*
    **/test_*.py
    src/generated.py
""")
        reader = _config_reader()
        assert reader("do_not_mutate", []) == [
            "**/migrations/*",
            "**/test_*.py",
            "src/generated.py",
        ]

    def test_parses_bool_values(self, in_tmp_dir: Path):
        (in_tmp_dir / "setup.cfg").write_text("""
[mutmut]
debug = true
""")
        reader = _config_reader()
        assert reader("debug", False) is True

        (in_tmp_dir / "setup.cfg").write_text("""
[mutmut]
debug = 1
""")
        reader = _config_reader()
        assert reader("debug", False) is True

        (in_tmp_dir / "setup.cfg").write_text("""
[mutmut]
debug = false
""")
        reader = _config_reader()
        assert reader("debug", False) is False

    def test_parses_int_values(self, in_tmp_dir: Path):
        (in_tmp_dir / "setup.cfg").write_text("""
[mutmut]
max_stack_depth = 42
""")
        reader = _config_reader()
        assert reader("max_stack_depth", -1) == 42

    def test_returns_default_for_missing_section(self, in_tmp_dir: Path):
        (in_tmp_dir / "setup.cfg").write_text("""
[other]
foo = bar
""")
        reader = _config_reader()
        assert reader("debug", False) is False

    def test_returns_default_for_missing_key(self, in_tmp_dir: Path):
        (in_tmp_dir / "setup.cfg").write_text("""
[mutmut]
debug = true
""")
        reader = _config_reader()
        assert reader("nonexistent", "default") == "default"


class TestConfigReaderPriority:
    def test_pyproject_toml_takes_precedence(self, in_tmp_dir: Path):
        (in_tmp_dir / "pyproject.toml").write_text("""
[tool.mutmut]
debug = true
""")
        (in_tmp_dir / "setup.cfg").write_text("""
[mutmut]
debug = false
""")
        reader = _config_reader()
        assert reader("debug", False) is True


class TestGuessPathsToMutate:
    def test_guesses_lib_directory(self, in_tmp_dir: Path):
        (in_tmp_dir / "lib").mkdir()
        assert _guess_source_paths() == ["lib"]

    def test_guesses_src_directory(self, in_tmp_dir: Path):
        (in_tmp_dir / "src").mkdir()
        assert _guess_source_paths() == ["src"]

    def test_prefers_lib_over_src(self, in_tmp_dir: Path):
        (in_tmp_dir / "lib").mkdir()
        (in_tmp_dir / "src").mkdir()
        assert _guess_source_paths() == ["lib"]

    def test_guesses_directory_matching_cwd_name(self, in_tmp_dir: Path):
        # tmp_path has a random name, create a subdir matching it
        dir_name = in_tmp_dir.name
        (in_tmp_dir / dir_name).mkdir()
        assert _guess_source_paths() == [dir_name]

    def test_guesses_py_file_matching_cwd_name(self, in_tmp_dir: Path):
        dir_name = in_tmp_dir.name
        (in_tmp_dir / f"{dir_name}.py").touch()
        assert _guess_source_paths() == [f"{dir_name}.py"]

    def test_raises_when_cannot_guess(self, in_tmp_dir: Path):
        with pytest.raises(FileNotFoundError, match="Could not figure out"):
            _guess_source_paths()


class TestLoadConfig:
    def test_loads_all_config_values(self, in_tmp_dir: Path):
        (in_tmp_dir / "pyproject.toml").write_text("""
[tool.mutmut]
debug = true
max_stack_depth = 10
source_paths = ["src"]
only_mutate=["**/foo.py"]
do_not_mutate = ["**/test_*.py"]
pytest_add_cli_args = ["-x", "--tb=short"]
pytest_add_cli_args_test_selection = ["--no-header"]
also_copy = ["fixtures"]
mutate_only_covered_lines = true
type_check_command = ["mypy", "--strict"]
timeout_multiplier = 5.0
timeout_constant = 0.5
""")
        (in_tmp_dir / "src").mkdir()

        config = _load_config()

        assert config.debug is True
        assert config.max_stack_depth == 10
        assert config.source_paths == [Path("src")]
        assert config.only_mutate == ["**/foo.py"]
        assert config.do_not_mutate == ["**/test_*.py"]
        assert config.pytest_add_cli_args == ["-x", "--tb=short"]
        assert config.pytest_add_cli_args_test_selection == ["--no-header"]
        assert Path("fixtures") in config.also_copy
        assert config.mutate_only_covered_lines is True
        assert config.type_check_command == ["mypy", "--strict"]
        assert config.timeout_multiplier == 5.0
        assert config.timeout_constant == 0.5

    def test_uses_defaults_when_no_config(self, in_tmp_dir: Path):
        (in_tmp_dir / "src").mkdir()

        config = _load_config()

        assert config.debug is False
        assert config.max_stack_depth == -1
        assert config.source_paths == [Path("src")]
        assert config.only_mutate == []
        assert config.do_not_mutate == []
        assert config.mutate_only_covered_lines is False
        assert config.timeout_multiplier == 15.0
        assert config.timeout_constant == 1.0
        assert config.type_check_command == []

    def test_also_copy_includes_defaults(self, in_tmp_dir: Path):
        (in_tmp_dir / "src").mkdir()

        config = _load_config()

        assert Path("tests/") in config.also_copy
        assert Path("test/") in config.also_copy
        assert Path("setup.cfg") in config.also_copy
        assert Path("pyproject.toml") in config.also_copy
