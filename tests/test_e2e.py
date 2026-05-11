from ai_pr_attribution.diff_parser import parse_unified_diff
from ai_pr_attribution.events import read_chunks, write_chunks
from ai_pr_attribution.matcher import attribute_lines, summarize
from ai_pr_attribution.report import render_markdown
from tests.test_matcher import chunk


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
    assert "AI PR Attribution" in comment
    assert "| claude_code | 1 |" in comment
