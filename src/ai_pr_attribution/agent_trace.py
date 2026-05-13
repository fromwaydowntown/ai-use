"""Agent Trace format adapter.

Agent Trace is an open specification proposed by Cursor (RFC, Feb 2026) for
vendor-neutral AI code attribution. This module converts between our internal
AiCodeChunk format and Agent Trace JSON so attribution data can be shared with
any tool that adopts the spec.

Spec: https://www.infoq.com/news/2026/02/agent-trace-cursor/
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_pr_attribution.schema import AiCodeChunk, ToolName

AGENT_TRACE_VERSION = "0.1"

# Map our tool names to Agent Trace agent identifiers
_TOOL_TO_AGENT: dict[str, str] = {
    "claude_code": "anthropic.claude-code",
    "cursor": "anysphere.cursor",
    "codex": "openai.codex",
}

_AGENT_TO_TOOL: dict[str, ToolName] = {
    "anthropic.claude-code": "claude_code",
    "anysphere.cursor": "cursor",
    "openai.codex": "codex",
}


def chunk_to_agent_trace(chunk: AiCodeChunk) -> dict[str, Any]:
    """Convert one AiCodeChunk to an Agent Trace record."""
    agent_id = _TOOL_TO_AGENT.get(chunk.tool, chunk.tool)
    return {
        "spec_version": AGENT_TRACE_VERSION,
        "trace_id": chunk.chunk_id,
        "timestamp": chunk.event_time,
        "contributor": {
            "type": "ai",
            "agent": agent_id,
        },
        "file": chunk.file_path,
        "repo_id": chunk.repo_id,
        "commit_base": chunk.commit_base,
        # Content hashes let downstream tools track lines through refactors.
        # We store SHA-256 of normalized lines — same approach the spec recommends.
        "content_hashes": list(chunk.line_hashes),
        "x-ai-pr-attribution": {
            "schema_version": 1,
            "chunk_id": chunk.chunk_id,
        },
    }


def chunk_from_agent_trace(record: dict[str, Any]) -> AiCodeChunk:
    """Convert an Agent Trace record to an AiCodeChunk.

    Unknown agent identifiers are stored verbatim in metadata and the tool
    field falls back to 'claude_code' so the rest of the pipeline keeps working.
    """
    agent = record.get("contributor", {}).get("agent", "")
    tool: ToolName = _AGENT_TO_TOOL.get(agent, "claude_code")

    chunk_id = (
        record.get("x-ai-pr-attribution", {}).get("chunk_id")
        or record.get("trace_id")
        or str(uuid.uuid4())
    )

    timestamp = record.get("timestamp") or datetime.now(timezone.utc).isoformat()

    return AiCodeChunk(
        tool=tool,
        repo_id=str(record.get("repo_id", "")),
        commit_base=record.get("commit_base"),
        file_path=str(record.get("file", "unknown")),
        event_time=str(timestamp),
        chunk_id=str(chunk_id),
        line_hashes=tuple(str(h) for h in record.get("content_hashes", [])),
        metadata={"agent_trace_agent": agent} if agent else {},
    )


def export_ndjson(chunks: list[AiCodeChunk], dest: Path) -> None:
    """Write chunks as Agent Trace NDJSON."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk_to_agent_trace(chunk), sort_keys=True) + "\n")


def import_ndjson(src: Path) -> list[AiCodeChunk]:
    """Read an Agent Trace NDJSON file and return AiCodeChunks."""
    if not src.exists():
        return []
    chunks: list[AiCodeChunk] = []
    with src.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(chunk_from_agent_trace(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                raise ValueError(f"invalid Agent Trace record at {src}:{lineno}: {exc}") from exc
    return chunks
