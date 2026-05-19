"""Tests for the trend-focused markdown dashboard renderer."""
import subprocess
from datetime import datetime, timedelta, timezone

from ai_use.dashboard_markdown import (
    DASHBOARD_MARKER,
    render_dashboard_markdown,
)
from ai_use.events import write_chunks
from ai_use.hashing import hash_lines
from ai_use.schema import AiCodeChunk


def _chunk(file_path, lines, tool="cursor", event_time=None):
    if event_time is None:
        event_time = datetime.now(timezone.utc).isoformat()
    return AiCodeChunk(
        tool=tool, repo_id="r", commit_base="c", file_path=file_path,
        event_time=event_time, chunk_id=f"{tool}-{file_path}-{event_time}",
        line_hashes=hash_lines(lines), metadata={},
    )


def _init_repo(path):
    path.mkdir(exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    return path


def _make_commit(repo, filename, content):
    (repo / filename).write_text(content)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "x"], cwd=repo, check=True, capture_output=True)


def test_empty_events_renders_placeholder(tmp_path):
    events = tmp_path / "events.ndjson"
    events.write_text("")
    md = render_dashboard_markdown(events)
    assert "No attribution events recorded yet" in md
    assert DASHBOARD_MARKER in md


def test_kpi_cards_present(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [_chunk("a.py", "x\ny")])
    md = render_dashboard_markdown(events)
    assert "## At a glance" in md
    assert "AI share this week" in md
    assert "Active tools this week" in md


def test_pct_trend_chart_rendered(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [_chunk("a.py", "x")])
    md = render_dashboard_markdown(events)
    assert "## AI share over time" in md
    assert "xychart-beta" in md
    assert '"%"' in md  # y-axis label


def test_per_tool_trend_charts(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [
        _chunk("a.py", "x\ny\nz", "claude_code"),
        _chunk("b.py", "p", "codex"),
    ])
    md = render_dashboard_markdown(events)
    assert "## By tool over time" in md
    assert "### Claude Code" in md
    assert "### Codex" in md
    # tools with no data shouldn't appear
    assert "### Cursor" not in md


def test_current_tool_split_section(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [
        _chunk("a.py", "x\ny\nz", "claude_code"),
        _chunk("b.py", "p", "codex"),
    ])
    md = render_dashboard_markdown(events)
    assert "## This week by tool" in md
    assert "Claude Code" in md
    assert "Codex" in md


def test_tool_labels_humanized(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [_chunk("a.py", "x", "claude_code")])
    md = render_dashboard_markdown(events)
    assert "Claude Code" in md
    assert "claude_code" not in md


def test_marker_embedded(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [_chunk("a.py", "x")])
    assert DASHBOARD_MARKER in render_dashboard_markdown(events)


def test_no_file_or_contributor_sections(tmp_path):
    """Trend-focused dashboard: file-level and per-contributor detail removed."""
    events = tmp_path / "events.ndjson"
    write_chunks(events, [_chunk("a.py", "x")])
    md = render_dashboard_markdown(events)
    assert "Top files" not in md
    assert "By contributor" not in md


def test_pct_uses_git_total_when_repo_provided(tmp_path):
    """The dashboard should compute AI% as ai_lines / git_total_lines per week.

    With the matcher fix (lines below MIN_HASHABLE_LENGTH are skipped), we
    write longer lines so the chunk actually registers hashes.
    """
    repo = _init_repo(tmp_path / "repo")
    # 5 substantive lines actually committed to git
    long_lines = "\n".join([f"line number {i} is here" for i in range(1, 6)])
    _make_commit(repo, "file.py", long_lines + "\n")

    events = repo / "events.ndjson"
    # AI was responsible for 2 of those 5 lines
    ai_lines = "\n".join([f"line number {i} is here" for i in range(1, 3)])
    write_chunks(events, [_chunk("file.py", ai_lines)])

    md = render_dashboard_markdown(events, repo=repo)
    # 2/5 = 40%. Must appear as a concrete percentage in the KPI section.
    assert "**40%**" in md, f"Expected '**40%**' in dashboard output, got:\n{md}"


def test_render_dashboard_cli_writes_file(tmp_path):
    from ai_use.cli import main
    events = tmp_path / "events.ndjson"
    write_chunks(events, [_chunk("a.py", "x")])
    output = tmp_path / "docs" / "AI_USAGE.md"

    rc = main([
        "render-dashboard", "--repo", str(tmp_path),
        "--events-file", str(events), "--output", str(output),
    ])
    assert rc == 0
    assert "# AI Usage" in output.read_text()
