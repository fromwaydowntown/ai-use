import json

from ai_use.adapters import chunk_from_hook_payload, parse_hook_stdin
from ai_use.hashing import hash_line


def test_parse_hook_stdin_accepts_json_object():
    assert parse_hook_stdin('{"file_path":"x.py","text":"print(1)"}') == {"file_path": "x.py", "text": "print(1)"}


def test_parse_hook_stdin_wraps_plain_text():
    assert parse_hook_stdin("hello") == {"text": "hello"}


def test_cursor_payload_becomes_hash_only_chunk(tmp_path):
    payload = {"file_path": "app.py", "text": "print(1)", "model": "test-model"}
    event = chunk_from_hook_payload("cursor", tmp_path, payload)
    encoded = json.dumps(event.to_json())
    assert event.file_path == "app.py"
    assert event.line_hashes == (hash_line("print(1)"),)
    assert "print(1)" not in encoded
    assert event.metadata["model"] == "test-model"


def test_claude_code_payload_extracts_nested_tool_input_without_raw_metadata(tmp_path):
    payload = {
        "cwd": str(tmp_path),
        "hook_event_name": "PostToolUse",
        "session_id": "session-1",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp_path / "hook_test.py"),
            "content": 'def hook_test():\n    return "ok"\n',
        },
        "tool_response": {
            "content": 'def hook_test():\n    return "ok"\n',
            "filePath": str(tmp_path / "hook_test.py"),
        },
    }
    event = chunk_from_hook_payload("claude_code", tmp_path, payload)
    encoded = json.dumps(event.to_json())
    assert event.file_path.endswith("hook_test.py")
    assert event.line_hashes == (hash_line("def hook_test():"), hash_line('    return "ok"'))
    assert 'return "ok"' not in encoded
    assert "def hook_test():" not in encoded
    assert "tool_input" not in event.metadata
    assert "tool_response" not in event.metadata
    assert "tool_input" not in event.metadata["payload_keys"]
    assert "tool_response" not in event.metadata["payload_keys"]
    assert event.metadata["tool_name"] == "Write"
