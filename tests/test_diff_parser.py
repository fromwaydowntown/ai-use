from ai_pr_attribution.diff_parser import parse_unified_diff


def test_parse_added_lines_from_modified_file():
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 context
-old
+new
+another
"""
    lines = parse_unified_diff(diff)
    assert [(line.file_path, line.new_lineno, line.text) for line in lines] == [
        ("app.py", 2, "new"),
        ("app.py", 3, "another"),
    ]


def test_parse_added_file_and_ignores_headers():
    diff = """diff --git a/new.py b/new.py
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+first
+
"""
    lines = parse_unified_diff(diff)
    assert [(line.file_path, line.new_lineno, line.text) for line in lines] == [
        ("new.py", 1, "first"),
        ("new.py", 2, ""),
    ]
