"""End-to-end attribution tests covering all three tools."""
import json

import pytest

from ai_pr_attribution.adapters import chunk_from_hook_payload
from ai_pr_attribution.codex_session import chunks_from_codex_session
from ai_pr_attribution.diff_parser import parse_unified_diff
from ai_pr_attribution.events import read_chunks, write_chunks
from ai_pr_attribution.hashing import hash_lines
from ai_pr_attribution.matcher import attribute_lines, summarize
from ai_pr_attribution.report import render_markdown
from ai_pr_attribution.schema import AiCodeChunk


# ── helpers ──────────────────────────────────────────────────────────────────

def make_chunk(file_path: str, text: str, tool: str) -> AiCodeChunk:
    return AiCodeChunk(
        tool=tool, repo_id="repo", commit_base="abc", file_path=file_path,
        event_time="", chunk_id=f"{tool}-{file_path}", line_hashes=hash_lines(text),
    )


def make_diff(files: dict[str, list[str]]) -> str:
    parts = []
    for path, lines in files.items():
        parts += [
            f"diff --git a/{path} b/{path}",
            "--- /dev/null",
            f"+++ b/{path}",
            f"@@ -0,0 +1,{len(lines)} @@",
            *[f"+{l}" for l in lines],
        ]
    return "\n".join(parts)


AI_LINES = ["def hello():", '    return "hello"', "def add(a, b):", "    return a + b"]
HUMAN_LINES = ["import sys", "def main():", "    print(sys.argv)"]


# ── claude code ───────────────────────────────────────────────────────────────

def test_claude_code_hook_payload_attributed(tmp_path):
    payload = {
        "cwd": str(tmp_path),
        "hook_event_name": "PostToolUse",
        "session_id": "s1",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp_path / "ai.py"),
            "content": "\n".join(AI_LINES) + "\n",
        },
        "tool_response": {"content": "", "filePath": str(tmp_path / "ai.py")},
    }
    chunk = chunk_from_hook_payload("claude_code", tmp_path, payload)
    assert chunk.tool == "claude_code"
    assert len(chunk.line_hashes) == len(AI_LINES)

    diff = make_diff({"ai.py": AI_LINES, "human.py": HUMAN_LINES})
    attributions = attribute_lines(parse_unified_diff(diff), [chunk])
    summary = summarize(attributions)

    assert summary.by_tool.get("claude_code", 0) > 0
    assert summary.unmatched == len(HUMAN_LINES)


def test_claude_code_edit_tool_attributed(tmp_path):
    payload = {
        "cwd": str(tmp_path),
        "hook_event_name": "PostToolUse",
        "session_id": "s1",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tmp_path / "ai.py"),
            "new_string": "\n".join(AI_LINES) + "\n",
        },
        "tool_response": {"content": ""},
    }
    chunk = chunk_from_hook_payload("claude_code", tmp_path, payload)
    assert chunk.tool == "claude_code"
    assert len(chunk.line_hashes) > 0


# ── cursor ────────────────────────────────────────────────────────────────────

def test_cursor_hook_payload_attributed(tmp_path):
    payload = {"file_path": "ai.py", "text": "\n".join(AI_LINES), "model": "gpt-4o"}
    chunk = chunk_from_hook_payload("cursor", tmp_path, payload)
    assert chunk.tool == "cursor"
    assert chunk.file_path == "ai.py"
    assert chunk.metadata.get("model") == "gpt-4o"

    diff = make_diff({"ai.py": AI_LINES, "human.py": HUMAN_LINES})
    attributions = attribute_lines(parse_unified_diff(diff), [chunk])
    summary = summarize(attributions)

    assert summary.by_tool.get("cursor", 0) > 0
    assert summary.unmatched == len(HUMAN_LINES)


def test_cursor_no_raw_code_in_serialized_chunk(tmp_path):
    payload = {"file_path": "secret.py", "text": "SECRET_KEY = 'abc123'"}
    chunk = chunk_from_hook_payload("cursor", tmp_path, payload)
    serialized = json.dumps(chunk.to_json())
    assert "SECRET_KEY" not in serialized
    assert "abc123" not in serialized


# ── codex ─────────────────────────────────────────────────────────────────────

def test_codex_session_attributed(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "ai.py"

    session = tmp_path / "session.jsonl"
    event = {
        "timestamp": "2026-05-11T16:00:00Z",
        "payload": {
            "type": "patch_apply_end",
            "call_id": "c1",
            "turn_id": "t1",
            "changes": {
                str(target): {
                    "type": "update",
                    "unified_diff": "@@\n" + "".join(f"+{l}\n" for l in AI_LINES),
                }
            },
        },
    }
    session.write_text(json.dumps(event) + "\n")

    chunks = chunks_from_codex_session(session, repo)
    assert len(chunks) == 1
    assert chunks[0].tool == "codex"

    diff = make_diff({"ai.py": AI_LINES, "human.py": HUMAN_LINES})
    attributions = attribute_lines(parse_unified_diff(diff), chunks)
    summary = summarize(attributions)

    assert summary.by_tool.get("codex", 0) > 0
    assert summary.unmatched == len(HUMAN_LINES)


def test_codex_foreign_repo_not_attributed(tmp_path):
    """Codex events from a different repo must not bleed into attribution."""
    repo = tmp_path / "repo"
    repo.mkdir()
    other_repo = tmp_path / "other-project"
    other_repo.mkdir()

    session = tmp_path / "session.jsonl"
    event = {
        "timestamp": "2026-05-11T16:00:00Z",
        "payload": {
            "type": "patch_apply_end",
            "call_id": "c1",
            "changes": {
                str(other_repo / "ai.py"): {  # file is in a different repo
                    "type": "update",
                    "unified_diff": "@@\n" + "".join(f"+{l}\n" for l in AI_LINES),
                }
            },
        },
    }
    session.write_text(json.dumps(event) + "\n")

    chunks = chunks_from_codex_session(session, repo)
    assert chunks == [], "Foreign-repo Codex chunks must be discarded"

    diff = make_diff({"ai.py": AI_LINES})
    attributions = attribute_lines(parse_unified_diff(diff), chunks)
    summary = summarize(attributions)
    assert summary.by_tool == {}, "No attribution expected from foreign Codex session"


# ── multi-tool ────────────────────────────────────────────────────────────────

def test_mixed_tools_attributed_correctly(tmp_path):
    events_file = tmp_path / "events.ndjson"
    write_chunks(events_file, [
        make_chunk("claude.py", "claude line", "claude_code"),
        make_chunk("cursor.py", "cursor line", "cursor"),
        make_chunk("codex.py", "codex line", "codex"),
    ])

    diff = make_diff({
        "claude.py": ["claude line"],
        "cursor.py": ["cursor line"],
        "codex.py": ["codex line"],
        "human.py": ["human line"],
    })
    attributions = attribute_lines(parse_unified_diff(diff), read_chunks(events_file))
    summary = summarize(attributions)

    assert summary.by_tool == {"claude_code": 1, "cursor": 1, "codex": 1}
    assert summary.unmatched == 1
    assert summary.attribution_percent == 75.0


def test_render_shows_all_tools(tmp_path):
    events_file = tmp_path / "events.ndjson"
    write_chunks(events_file, [
        make_chunk("a.py", "claude line", "claude_code"),
        make_chunk("b.py", "cursor line", "cursor"),
        make_chunk("c.py", "codex line", "codex"),
    ])
    diff = make_diff({
        "a.py": ["claude line"], "b.py": ["cursor line"], "c.py": ["codex line"],
    })
    attributions = attribute_lines(parse_unified_diff(diff), read_chunks(events_file))
    comment = render_markdown(summarize(attributions), attributions)

    assert "Claude Code" in comment
    assert "Cursor" in comment
    assert "Codex" in comment
