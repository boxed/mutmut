from click.testing import CliRunner

from mutmut import __version__
from mutmut.__main__ import cli


def test_cli_version():
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output
