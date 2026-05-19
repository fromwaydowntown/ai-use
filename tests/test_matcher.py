from ai_use.diff_parser import parse_unified_diff
from ai_use.hashing import hash_lines
from ai_use.matcher import attribute_lines, summarize
from ai_use.schema import AiCodeChunk


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


def test_matcher_attributes_exact_file_match():
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,0 +1,2 @@
+def hello_world():
+human-written long line here
"""
    added = parse_unified_diff(diff)
    results = attribute_lines(added, [chunk("app.py", "def hello_world():")])
    assert [r.confidence for r in results] == ["exact_file_match", "unmatched"]
    summary = summarize(results)
    assert summary.total_added_lines == 2
    assert summary.attributed_lines == 1
    assert summary.by_tool == {"cursor": 1}


def test_matcher_does_not_cross_file_match():
    """A line written by AI in file A should not be attributed when it
    appears in PR file B — too risky for boilerplate like `import json`."""
    diff = """diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,0 +1,1 @@
+def shared_function():
"""
    added = parse_unified_diff(diff)
    results = attribute_lines(added, [chunk("a.py", "def shared_function():", "codex")])
    assert results[0].confidence == "unmatched"
    summary = summarize(results)
    assert summary.attributed_lines == 0


def test_matcher_skips_blank_and_short_lines():
    """Blank lines and very short lines normalize to the NULL_HASH and are
    always reported as unattributed — protects against trivial collisions."""
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,0 +1,4 @@
+
+}
+pass
+def real_function():
"""
    added = parse_unified_diff(diff)
    # AI chunk happens to contain the same trivial lines
    results = attribute_lines(added, [chunk("app.py", "\n}\npass\ndef real_function():")])
    confidences = [r.confidence for r in results]
    # only the substantive line is attributed; blanks/short are unmatched
    assert confidences == ["unmatched", "unmatched", "unmatched", "exact_file_match"]
