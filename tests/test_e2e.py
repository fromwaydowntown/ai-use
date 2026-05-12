from ai_pr_attribution.diff_parser import parse_unified_diff
from ai_pr_attribution.events import read_chunks, write_chunks
from ai_pr_attribution.matcher import attribute_lines, summarize
from ai_pr_attribution.report import render_markdown
from ai_pr_attribution.hashing import hash_lines
from ai_pr_attribution.schema import AiCodeChunk


def chunk(file_path: str, text: str, tool: str = "cursor") -> AiCodeChunk:
    return AiCodeChunk(
        tool=tool, repo_id="repo", commit_base="abc", file_path=file_path,
        event_time="", chunk_id=f"{tool}-{file_path}", line_hashes=hash_lines(text),
    )


def test_end_to_end_summary_from_fixture(tmp_path):
    events = tmp_path / "events.ndjson"
    write_chunks(events, [chunk("app.py", "ai line", "claude_code")])
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,0 +1,2 @@
+ai line
+human line
"""
    attributions = attribute_lines(parse_unified_diff(diff), read_chunks(events))
    summary = summarize(attributions)
    comment = render_markdown(summary, attributions)
    assert summary.attribution_percent == 50.0
    assert "AI attribution" in comment
    assert "Claude Code" in comment
