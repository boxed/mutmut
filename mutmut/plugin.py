from typing import TYPE_CHECKING
from typing import Optional

from .loader import install


if TYPE_CHECKING:
    from _pytest.config import Config
    from _pytest.config import PytestPluginManager
    from _pytest.config.argparsing import Parser


def pytest_configure(config: "Config") -> None:
    mutant_id: Optional[int] = config.getoption("mutant_id", default=None)

    if mutant_id is None:
        return

    install(mutant_id)


def pytest_addoption(parser: "Parser", pluginmanager: "PytestPluginManager") -> None:
    parser.addoption("--mutant-id", dest="mutant_id", type=int)
