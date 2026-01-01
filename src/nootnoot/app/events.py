from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class RunEvent:
    event: str
    data: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"event": self.event, "data": dict(self.data)}


class EventSink(Protocol):
    def emit(self, event: RunEvent) -> None: ...


class ListEventSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def emit(self, event: RunEvent) -> None:
        self.events.append(event)


def emit_event(sink: EventSink | None, event: str, data: dict[str, Any]) -> None:
    if sink is None:
        return
    sink.emit(RunEvent(event=event, data=data))
