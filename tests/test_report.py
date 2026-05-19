"""Tests for markdown comment renderer, check-run renderer, and JSON summary."""
import json

from ai_use.diff_parser import parse_unified_diff
from ai_use.hashing import hash_lines
from ai_use.matcher import attribute_lines, summarize
from ai_use.report import (
    COMMENT_MARKER,
    render_check_run,
    render_markdown,
    summary_to_json,
)
from ai_use.schema import AiCodeChunk


def _chunk(file_path: str, text: str, tool: str = "cursor") -> AiCodeChunk:
    return AiCodeChunk(
        tool=tool, repo_id="r", commit_base="c", file_path=file_path,
        event_time="", chunk_id=f"{tool}-{file_path}", line_hashes=hash_lines(text),
    )


def _summary_from(diff: str, chunks: list[AiCodeChunk]):
    attributions = attribute_lines(parse_unified_diff(diff), chunks)
    return summarize(attributions), attributions


SAMPLE_DIFF = """diff --git a/a.py b/a.py
--- /dev/null
+++ b/a.py
@@ -0,0 +1,2 @@
+def ai_written_function():
+def human_written_function():
"""

# Text used as the "AI" line in chunks — must match the AI line in SAMPLE_DIFF.
AI_TEXT = "def ai_written_function():"


# ── markdown comment ─────────────────────────────────────────────────────────

def test_markdown_marker_present():
    summary, attrs = _summary_from(SAMPLE_DIFF, [_chunk("a.py", AI_TEXT, "claude_code")])
    assert COMMENT_MARKER in render_markdown(summary, attrs)


def test_markdown_progress_bar():
    summary, attrs = _summary_from(SAMPLE_DIFF, [_chunk("a.py", AI_TEXT, "cursor")])
    comment = render_markdown(summary, attrs)
    assert "█" in comment
    assert "░" in comment


def test_markdown_final_tag_only_on_merge():
    summary, attrs = _summary_from(SAMPLE_DIFF, [_chunk("a.py", AI_TEXT)])
    assert "Final" not in render_markdown(summary, attrs, final=False)
    assert "Final" in render_markdown(summary, attrs, final=True)


def test_markdown_no_matches_when_empty():
    summary, attrs = _summary_from(SAMPLE_DIFF, [])
    comment = render_markdown(summary, attrs)
    assert "no matches" in comment
    assert "0%" in comment


def test_markdown_tool_labels_humanized():
    summary, attrs = _summary_from(SAMPLE_DIFF, [_chunk("a.py", AI_TEXT, "claude_code")])
    comment = render_markdown(summary, attrs)
    assert "Claude Code" in comment
    assert "claude_code" not in comment


# ── check run ────────────────────────────────────────────────────────────────

def test_check_run_title_has_pct_and_tool_summary():
    summary, attrs = _summary_from(SAMPLE_DIFF, [_chunk("a.py", AI_TEXT, "claude_code")])
    title, body = render_check_run(summary, attrs)
    assert "50% AI" in title
    assert "1/2 lines" in title
    assert "Claude Code 1L" in title


def test_check_run_summary_has_per_tool_and_per_file_tables():
    summary, attrs = _summary_from(SAMPLE_DIFF, [_chunk("a.py", AI_TEXT, "cursor")])
    _, body = render_check_run(summary, attrs)
    assert "### By tool" in body
    assert "### By file" in body
    assert "### Confidence" in body
    assert "| Cursor | 1 |" in body
    assert "`a.py`" in body


def test_check_run_final_changes_label():
    summary, attrs = _summary_from(SAMPLE_DIFF, [_chunk("a.py", AI_TEXT)])
    title_preview, _ = render_check_run(summary, attrs, final=False)
    title_final, _ = render_check_run(summary, attrs, final=True)
    assert title_preview.startswith("Preview:")
    assert title_final.startswith("Final:")


def test_check_run_no_matches_when_empty():
    summary, attrs = _summary_from(SAMPLE_DIFF, [])
    title, body = render_check_run(summary, attrs)
    assert "no AI matches" in title
    assert "0%" in body


def test_check_run_marker_embedded():
    summary, attrs = _summary_from(SAMPLE_DIFF, [_chunk("a.py", AI_TEXT)])
    _, body = render_check_run(summary, attrs)
    assert COMMENT_MARKER in body


# ── JSON summary ─────────────────────────────────────────────────────────────

def test_summary_to_json_round_trip():
    summary, _ = _summary_from(SAMPLE_DIFF, [_chunk("a.py", AI_TEXT, "codex")])
    payload = json.loads(summary_to_json(summary))
    assert payload["total_added_lines"] == 2
    assert payload["attributed_lines"] == 1
    assert payload["attribution_percent"] == 50.0
    assert payload["by_tool"] == {"codex": 1}


def test_zero_percent_when_no_added_lines():
    summary, attrs = _summary_from("", [_chunk("a.py", AI_TEXT)])
    comment = render_markdown(summary, attrs)
    assert "0%" in comment
