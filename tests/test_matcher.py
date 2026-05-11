from ai_pr_attribution.diff_parser import parse_unified_diff
from ai_pr_attribution.hashing import hash_lines
from ai_pr_attribution.matcher import attribute_lines, summarize
from ai_pr_attribution.schema import AiCodeChunk


def chunk(file_path: str, text: str, tool: str = "cursor") -> AiCodeChunk:
    return AiCodeChunk(
        tool=tool,
        repo_id="repo",
        commit_base="abc",
        file_path=file_path,
        event_time="2026-05-11T00:00:00Z",
        chunk_id=f"{tool}-{file_path}",
        line_hashes=hash_lines(text),
    )


def test_matcher_reports_exact_cross_file_and_unmatched():
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,0 +1,3 @@
+exact
+cross
+human
"""
    added = parse_unified_diff(diff)
    results = attribute_lines(added, [chunk("app.py", "exact"), chunk("other.py", "cross", "codex")])
    assert [result.confidence for result in results] == ["exact_file_match", "cross_file_match", "unmatched"]
    summary = summarize(results)
    assert summary.total_added_lines == 3
    assert summary.attributed_lines == 2
    assert summary.by_tool == {"codex": 1, "cursor": 1}
