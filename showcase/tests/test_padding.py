import pytest

from rich.padding import Padding
from rich.console import Console, ConsoleOptions
from rich.style import Style
from rich.segment import Segment


def test_repr():
    padding = Padding("foo", (1, 2))
    assert isinstance(repr(padding), str)


def test_indent():
    indent_result = Padding.indent("test", 4)
    assert indent_result.top == 0
    assert indent_result.right == 0
    assert indent_result.bottom == 0
    assert indent_result.left == 4


def test_unpack():
    assert Padding.unpack(3) == (3, 3, 3, 3)
    assert Padding.unpack((3,)) == (3, 3, 3, 3)
    assert Padding.unpack((3, 4)) == (3, 4, 3, 4)
    assert Padding.unpack((3, 4, 5, 6)) == (3, 4, 5, 6)
    with pytest.raises(ValueError):
        Padding.unpack((1, 2, 3))


def test_expand_false():
    console = Console(width=100, color_system=None)
    console.begin_capture()
    console.print(Padding("foo", 1, expand=False))
    assert console.end_capture() == "     \n foo \n     \n"


def test_rich_console():
    renderable = "test renderable"
    style = Style(color="red")
    options = ConsoleOptions(
        legacy_windows=False,
        min_width=10,
        max_width=20,
        is_terminal=False,
        encoding="utf-8",
    )

    expected_outputs = [
        Segment(renderable, style=style),
        Segment(" " * (20 - len(renderable)), style=style),
        Segment("\n", style=None),
    ]
    padding_generator = Padding(renderable, style=style).__rich_console__(
        Console(), options
    )
    for output, expected in zip(padding_generator, expected_outputs):
        assert output == expected
