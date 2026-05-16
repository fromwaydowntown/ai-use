"""Tests for Agent Trace format adapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_pr_attribution.agent_trace import (
    AGENT_TRACE_VERSION,
    chunk_from_agent_trace,
    chunk_to_agent_trace,
    export_ndjson,
    import_ndjson,
)
from ai_pr_attribution.schema import AiCodeChunk


def _make_chunk(**kwargs) -> AiCodeChunk:
    defaults = dict(
        tool="claude_code",
        repo_id="repo-abc",
        commit_base="deadbeef",
        file_path="src/foo.py",
        event_time="2026-01-01T00:00:00+00:00",
        chunk_id="chunk-123",
        line_hashes=("aaa", "bbb", "ccc"),
        metadata={},
    )
    defaults.update(kwargs)
    return AiCodeChunk(**defaults)


class TestChunkToAgentTrace:
    def test_spec_version(self):
        record = chunk_to_agent_trace(_make_chunk())
        assert record["spec_version"] == AGENT_TRACE_VERSION

    def test_contributor_type_is_ai(self):
        record = chunk_to_agent_trace(_make_chunk())
        assert record["contributor"]["type"] == "ai"

    def test_claude_code_agent_id(self):
        record = chunk_to_agent_trace(_make_chunk(tool="claude_code"))
        assert record["contributor"]["agent"] == "anthropic.claude-code"

    def test_cursor_agent_id(self):
        record = chunk_to_agent_trace(_make_chunk(tool="cursor"))
        assert record["contributor"]["agent"] == "anysphere.cursor"

    def test_codex_agent_id(self):
        record = chunk_to_agent_trace(_make_chunk(tool="codex"))
        assert record["contributor"]["agent"] == "openai.codex"

    def test_content_hashes_preserved(self):
        chunk = _make_chunk(line_hashes=("h1", "h2", "h3"))
        record = chunk_to_agent_trace(chunk)
        assert record["content_hashes"] == ["h1", "h2", "h3"]

    def test_trace_id_matches_chunk_id(self):
        chunk = _make_chunk(chunk_id="my-chunk")
        record = chunk_to_agent_trace(chunk)
        assert record["trace_id"] == "my-chunk"

    def test_extension_namespace_present(self):
        record = chunk_to_agent_trace(_make_chunk())
        assert "x-ai-pr-attribution" in record


class TestChunkFromAgentTrace:
    def test_roundtrip(self):
        original = _make_chunk()
        record = chunk_to_agent_trace(original)
        recovered = chunk_from_agent_trace(record)
        assert recovered.tool == original.tool
        assert recovered.line_hashes == original.line_hashes
        assert recovered.chunk_id == original.chunk_id
        assert recovered.file_path == original.file_path

    def test_unknown_agent_falls_back_to_claude_code(self):
        record = {
            "spec_version": "0.1",
            "trace_id": "t1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "contributor": {"type": "ai", "agent": "unknown.vendor.tool"},
            "file": "src/bar.py",
            "repo_id": "repo-xyz",
            "commit_base": None,
            "content_hashes": ["h1"],
        }
        chunk = chunk_from_agent_trace(record)
        assert chunk.tool == "claude_code"
        assert chunk.metadata.get("agent_trace_agent") == "unknown.vendor.tool"

    def test_missing_optional_fields(self):
        record = {
            "contributor": {"type": "ai", "agent": "anthropic.claude-code"},
            "file": "main.py",
            "content_hashes": [],
        }
        chunk = chunk_from_agent_trace(record)
        assert chunk.file_path == "main.py"
        assert chunk.line_hashes == ()


class TestNdjsonRoundtrip:
    def test_export_then_import(self, tmp_path):
        chunks = [
            _make_chunk(chunk_id="c1", line_hashes=("h1", "h2")),
            _make_chunk(tool="cursor", chunk_id="c2", line_hashes=("h3",)),
        ]
        dest = tmp_path / "agent-trace.ndjson"
        export_ndjson(chunks, dest)

        assert dest.exists()
        lines = dest.read_text().strip().splitlines()
        assert len(lines) == 2

        recovered = import_ndjson(dest)
        assert len(recovered) == 2
        assert recovered[0].chunk_id == "c1"
        assert recovered[1].tool == "cursor"

    def test_import_nonexistent_file(self, tmp_path):
        result = import_ndjson(tmp_path / "missing.ndjson")
        assert result == []

    def test_import_invalid_json_raises(self, tmp_path):
        bad = tmp_path / "bad.ndjson"
        bad.write_text("not json\n")
        with pytest.raises(ValueError, match="invalid Agent Trace record"):
            import_ndjson(bad)
