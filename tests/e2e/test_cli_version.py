from click.testing import CliRunner

from nootnoot import __version__
from nootnoot.cli import cli


def test_cli_version():
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output
