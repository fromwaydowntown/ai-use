"""Tests for the markdown comment renderer and JSON summary."""
import json

from ai_pr_attribution.diff_parser import parse_unified_diff
from ai_pr_attribution.hashing import hash_lines
from ai_pr_attribution.matcher import attribute_lines, summarize
from ai_pr_attribution.report import COMMENT_MARKER, render_markdown, summary_to_json
from ai_pr_attribution.schema import AiCodeChunk


def _summary_from(diff: str, chunks: list[AiCodeChunk]):
    attributions = attribute_lines(parse_unified_diff(diff), chunks)
    return summarize(attributions), attributions


def _chunk(file_path: str, text: str, tool: str = "cursor") -> AiCodeChunk:
    return AiCodeChunk(
        tool=tool, repo_id="r", commit_base="c", file_path=file_path,
        event_time="", chunk_id=f"{tool}-{file_path}", line_hashes=hash_lines(text),
    )


SAMPLE_DIFF = """diff --git a/a.py b/a.py
--- /dev/null
+++ b/a.py
@@ -0,0 +1,2 @@
+ai
+human
"""


def test_marker_present_for_idempotent_updates():
    summary, attrs = _summary_from(SAMPLE_DIFF, [_chunk("a.py", "ai", "claude_code")])
    comment = render_markdown(summary, attrs)
    assert COMMENT_MARKER in comment


def test_renders_progress_bar():
    summary, attrs = _summary_from(SAMPLE_DIFF, [_chunk("a.py", "ai", "cursor")])
    comment = render_markdown(summary, attrs)
    assert "█" in comment  # at least some filled
    assert "░" in comment  # at least some empty


def test_final_tag_only_on_merge():
    summary, attrs = _summary_from(SAMPLE_DIFF, [_chunk("a.py", "ai")])
    assert "Final" not in render_markdown(summary, attrs, final=False)
    assert "Final" in render_markdown(summary, attrs, final=True)


def test_no_matches_when_attribution_empty():
    summary, attrs = _summary_from(SAMPLE_DIFF, [])
    comment = render_markdown(summary, attrs)
    assert "no matches" in comment
    assert "0%" in comment


def test_tool_labels_are_human_readable():
    summary, attrs = _summary_from(SAMPLE_DIFF, [_chunk("a.py", "ai", "claude_code")])
    comment = render_markdown(summary, attrs)
    assert "Claude Code" in comment
    assert "claude_code" not in comment


def test_summary_to_json_round_trip():
    summary, _ = _summary_from(SAMPLE_DIFF, [_chunk("a.py", "ai", "codex")])
    payload = json.loads(summary_to_json(summary))
    assert payload["total_added_lines"] == 2
    assert payload["attributed_lines"] == 1
    assert payload["attribution_percent"] == 50.0
    assert payload["by_tool"] == {"codex": 1}


def test_zero_percent_when_no_added_lines():
    summary, attrs = _summary_from("", [_chunk("a.py", "ai")])
    comment = render_markdown(summary, attrs)
    assert "0%" in comment
