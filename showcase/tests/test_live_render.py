import pytest
from rich.live_render import LiveRender
from rich.console import Console, ConsoleOptions
from rich.style import Style
from rich.segment import Segment


@pytest.fixture
def live_render():
    return LiveRender(renderable="my string")


def test_renderable(live_render):
    assert live_render.renderable == "my string"
    live_render.set_renderable("another string")
    assert live_render.renderable == "another string"


def test_position_cursor(live_render):
    assert str(live_render.position_cursor()) == ""
    live_render._shape = (80, 2)
    assert str(live_render.position_cursor()) == "\r\x1b[2K\x1b[1A\x1b[2K"


def test_restore_cursor(live_render):
    assert str(live_render.restore_cursor()) == ""
    live_render._shape = (80, 2)
    assert str(live_render.restore_cursor()) == "\r\x1b[1A\x1b[2K\x1b[1A\x1b[2K"


def test_rich_console(live_render):
    options = ConsoleOptions(
        legacy_windows=False,
        min_width=10,
        max_width=20,
        is_terminal=False,
        encoding="utf-8",
    )
    rich_console = live_render.__rich_console__(Console(), options)
    assert [Segment.control("my string", Style.parse("none"))] == list(rich_console)
    live_render.style = "red"
    rich_console = live_render.__rich_console__(Console(), options)
    assert [Segment.control("my string", Style.parse("red"))] == list(rich_console)
