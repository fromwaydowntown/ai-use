from ai_use.dashboard import build_summary, render_dashboard_html
from ai_use.events import write_chunks
from ai_use.schema import AiCodeChunk


def test_build_summary_groups_usage(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(
        events,
        [
            AiCodeChunk(
                tool="cursor",
                repo_id="repo",
                commit_base=None,
                file_path="app.py",
                event_time="2026-05-11T10:00:00Z",
                chunk_id="one",
                line_hashes=("a", "b"),
                metadata={"hook_event_name": "afterFileEdit"},
            ),
            AiCodeChunk(
                tool="claude_code",
                repo_id="repo",
                commit_base=None,
                file_path="app.py",
                event_time="2026-05-11T11:00:00Z",
                chunk_id="two",
                line_hashes=("c",),
                metadata={"hook_event_name": "PostToolUse"},
            ),
        ],
    )

    summary = build_summary(events)
    assert summary["total_chunks"] == 2
    assert summary["total_hashed_lines"] == 3
    assert summary["kpis"]["suggested_lines"] == 3
    assert summary["kpis"]["touched_files"] == 1
    assert summary["kpis"]["push_status"] == "n/a"
    assert summary["readiness"][0]["label"] == "Telemetry collected"
    assert summary["retention_by_tool"][0]["tool"] == "cursor"
    assert summary["retention_by_file"][0]["file_path"] == "app.py"
    assert summary["by_tool"] == {"claude_code": 1, "cursor": 1}
    assert summary["lines_by_tool"] == {"claude_code": 1, "cursor": 2}
    assert summary["top_files"] == [{"file_path": "app.py", "hashed_lines": 3}]
    assert summary["recent_chunks"][0]["tool"] == "claude_code"


def test_render_dashboard_html_contains_mount_points(tmp_path):
    html = render_dashboard_html(tmp_path)
    assert "Contribution Retention" in html
    assert "/api/summary" in html
    assert "merge-percent" in html
