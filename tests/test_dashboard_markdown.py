"""Tests for the markdown dashboard renderer."""
import json

from ai_pr_attribution.dashboard_markdown import DASHBOARD_MARKER, render_dashboard_markdown
from ai_pr_attribution.events import write_chunks
from ai_pr_attribution.hashing import hash_lines
from ai_pr_attribution.schema import AiCodeChunk


def _chunk(file_path, lines, tool="cursor", event_time="2026-05-11T10:00:00Z", author=None):
    metadata = {}
    if author:
        metadata["user_hash"] = author
    return AiCodeChunk(
        tool=tool, repo_id="r", commit_base="c", file_path=file_path,
        event_time=event_time, chunk_id=f"{tool}-{file_path}-{event_time}",
        line_hashes=hash_lines(lines), metadata=metadata,
    )


def test_empty_events_renders_placeholder(tmp_path):
    events = tmp_path / "events.ndjson"
    events.write_text("")
    md = render_dashboard_markdown(events)
    assert "No attribution events recorded yet" in md
    assert DASHBOARD_MARKER in md


def test_renders_marker_and_title(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [_chunk("a.py", "x")])
    md = render_dashboard_markdown(events)
    assert "# AI PR Attribution" in md
    assert DASHBOARD_MARKER in md


def test_by_tool_section_includes_all_tools(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [
        _chunk("a.py", "line1\nline2", "claude_code"),
        _chunk("b.py", "line3", "cursor"),
        _chunk("c.py", "line4", "codex"),
    ])
    md = render_dashboard_markdown(events)
    assert "Claude Code" in md
    assert "Cursor" in md
    assert "Codex" in md
    # no raw snake_case tool ids in output
    assert "claude_code" not in md


def test_includes_mermaid_pie_chart(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [_chunk("a.py", "x", "cursor")])
    md = render_dashboard_markdown(events)
    assert "```mermaid" in md
    assert "pie showData" in md


def test_includes_trend_chart_with_recent_weeks(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [
        _chunk("a.py", "x", "cursor", event_time="2026-01-05T10:00:00Z"),
        _chunk("a.py", "y", "cursor", event_time="2026-01-12T10:00:00Z"),
    ])
    md = render_dashboard_markdown(events)
    assert "xychart-beta" in md
    assert "2026-W01" in md or "2026-W02" in md


def test_top_files_section(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [
        _chunk("big.py", "a\nb\nc\nd", "cursor"),
        _chunk("small.py", "x", "cursor"),
    ])
    md = render_dashboard_markdown(events)
    assert "`big.py`" in md
    assert "`small.py`" in md


def test_by_author_section_when_authors_present(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [
        _chunk("a.py", "x", author="hash-alice"),
        _chunk("b.py", "y\nz", author="hash-bob"),
    ])
    md = render_dashboard_markdown(events)
    assert "By contributor" in md
    assert "hash-alice" in md
    assert "hash-bob" in md


def test_by_author_section_omitted_when_no_authors(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [_chunk("a.py", "x")])  # no user_hash metadata
    md = render_dashboard_markdown(events)
    assert "By contributor" not in md


def test_render_dashboard_cli_writes_file(tmp_path, monkeypatch):
    from ai_pr_attribution.cli import main
    events = tmp_path / "events.ndjson"
    write_chunks(events, [_chunk("a.py", "x")])
    output = tmp_path / "docs" / "AI_USAGE.md"

    rc = main([
        "render-dashboard", "--repo", str(tmp_path),
        "--events-file", str(events), "--output", str(output),
    ])
    assert rc == 0
    assert output.exists()
    assert "# AI PR Attribution" in output.read_text()
