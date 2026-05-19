import json

from ai_use.codex_session import chunks_from_codex_session, import_codex_session
from ai_use.hashing import hash_line


def test_chunks_from_codex_session_imports_patch_added_lines(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    session = tmp_path / "session.jsonl"
    target = repo / "app.py"
    event = {
        "timestamp": "2026-05-11T16:00:00Z",
        "payload": {
            "type": "patch_apply_end",
            "call_id": "call_1",
            "turn_id": "turn_1",
            "changes": {
                str(target): {
                    "type": "update",
                    "unified_diff": "@@ -1 +1,2 @@\n old\n+new\n+another\n",
                }
            },
        },
    }
    session.write_text(json.dumps(event) + "\n", encoding="utf-8")

    chunks = chunks_from_codex_session(session, repo)
    assert len(chunks) == 1
    assert chunks[0].tool == "codex"
    assert chunks[0].file_path == "app.py"
    assert chunks[0].line_hashes == (hash_line("new"), hash_line("another"))


def test_import_codex_session_is_idempotent(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    events = repo / ".ai-use" / "events.ndjson"
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps(
            {
                "timestamp": "2026-05-11T16:00:00Z",
                "payload": {
                    "type": "patch_apply_end",
                    "call_id": "call_1",
                    "changes": {
                        str(repo / "app.py"): {"type": "update", "unified_diff": "@@\n+new\n"},
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert import_codex_session(session, repo, events) == 1
    assert import_codex_session(session, repo, events) == 0
