"""CLI smoke tests: each subcommand parses and dispatches correctly."""
import json
import subprocess
import sys

import pytest

from ai_use.cli import main


def run_cli(*args, stdin: str = ""):
    """Invoke the CLI in a subprocess to capture stdout/stderr cleanly."""
    return subprocess.run(
        [sys.executable, "-m", "ai_use.cli", *args],
        input=stdin, capture_output=True, text=True,
    )


def test_no_command_exits_with_error():
    result = run_cli()
    assert result.returncode != 0


def test_install_creates_files(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    assert main(["install", "--repo", str(tmp_path)]) == 0
    assert (tmp_path / ".ai-use" / "hooks" / "collect-ai-event.sh").exists()
    assert (tmp_path / ".github" / "workflows" / "ai-use.yml").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / ".cursor" / "hooks.json").exists()


def test_install_with_collector_uses_classic_mode(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    assert main([
        "install", "--repo", str(tmp_path),
        "--collector-url", "https://collector.example",
    ]) == 0
    # github-native skipped → no workflow file
    assert not (tmp_path / ".github" / "workflows" / "ai-use.yml").exists()


def test_collect_hook_writes_event(tmp_path, monkeypatch):
    repo = tmp_path
    payload = json.dumps({"file_path": "a.py", "text": "x = 1 + 2 + 3"})
    monkeypatch.setattr("sys.stdin", _Stdin(payload))
    events_file = repo / "events.ndjson"
    assert main([
        "collect-hook", "--tool", "cursor", "--repo", str(repo),
        "--events-file", str(events_file),
    ]) == 0
    assert events_file.exists()
    line = events_file.read_text().strip()
    parsed = json.loads(line)
    assert parsed["tool"] == "cursor"
    assert parsed["file_path"] == "a.py"


def test_analyze_pr_emits_markdown(tmp_path, capsys, monkeypatch):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    diff = tmp_path / "pr.diff"
    diff.write_text("""diff --git a/a.py b/a.py
--- /dev/null
+++ b/a.py
@@ -0,0 +1,1 @@
+x = 1 + 2 + 3
""")
    events = tmp_path / "events.ndjson"
    events.write_text(json.dumps({
        "tool": "cursor", "repo_id": "r", "commit_base": "c",
        "file_path": "a.py", "event_time": "", "chunk_id": "c1",
        "line_hashes": [_hash_line("x = 1 + 2 + 3")], "metadata": {},
    }) + "\n")

    rc = main([
        "analyze-pr", "--repo", str(tmp_path), "--diff-file", str(diff),
        "--events-file", str(events),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "AI attribution" in out
    assert "Cursor" in out


def test_help_lists_all_subcommands():
    result = run_cli("--help")
    assert result.returncode == 0
    for sub in ["install", "collect-hook", "analyze-pr", "dashboard", "upload-ref"]:
        assert sub in result.stdout


# ── helpers ───────────────────────────────────────────────────────────────────

class _Stdin:
    def __init__(self, payload: str):
        self._payload = payload
    def read(self) -> str:
        return self._payload


def _hash_line(text: str) -> str:
    from ai_use.hashing import hash_line
    return hash_line(text)
