import io

from rich.console import Console
from rich.measure import Measurement
from rich.styled import Styled


def test_styled():
    styled_foo = Styled("foo", "on red")
    console = Console(file=io.StringIO(), force_terminal=True)
    assert Measurement.get(console, styled_foo, 80) == Measurement(3, 3)
    console.print(styled_foo)
    result = console.file.getvalue()
    expected = "\x1b[41mfoo\x1b[0m\n"
    assert result == expected
