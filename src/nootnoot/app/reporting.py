from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nootnoot.app.events import RunEvent

REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RunReport:
    summary: dict[str, int]
    mutants: list[dict[str, Any]]
    events: list[RunEvent]


def render_json_report(report: RunReport) -> str:
    payload = dict(
        schema_version=REPORT_SCHEMA_VERSION,
        summary=dict(report.summary),
        mutants=list(report.mutants),
        events=[event.as_dict() for event in report.events],
    )
    return json.dumps(payload, indent=2, sort_keys=True)
