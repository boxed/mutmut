import json

from nootnoot.events import RunEvent
from nootnoot.reporting import REPORT_SCHEMA_VERSION, RunReport, render_json_report


def test_render_json_report_schema() -> None:
    report = RunReport(
        summary={
            "killed": 1,
            "survived": 0,
            "timeout": 0,
            "no_tests": 0,
            "suspicious": 0,
            "skipped": 0,
            "not_checked": 0,
            "total": 1,
            "check_was_interrupted_by_user": 0,
            "segfault": 0,
        },
        mutants=[
            {
                "name": "pkg.mod.func__nootnoot_1",
                "path": "src/pkg/mod.py",
                "exit_code": 1,
                "status": "killed",
                "duration_seconds": 0.2,
                "estimated_duration_seconds": 0.1,
            }
        ],
        events=[
            RunEvent(
                event="session_started",
                data={"max_children": 2, "mutant_names": []},
            ),
            RunEvent(
                event="session_finished",
                data={"summary": {"killed": 1}, "duration_seconds": 1.0},
            ),
        ],
    )

    payload = json.loads(render_json_report(report))

    assert payload["schema_version"] == REPORT_SCHEMA_VERSION
    assert payload["summary"]["killed"] == 1
    assert payload["mutants"][0]["status"] == "killed"
    assert payload["events"][0]["event"] == "session_started"
