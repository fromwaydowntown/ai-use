from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_use.git_utils import current_head, repo_id
from ai_use.hashing import hash_lines
from ai_use.schema import AiCodeChunk, ToolName


TEXT_KEYS = ("text", "content", "new_string", "generated_text", "output", "diff")
FILE_KEYS = ("file_path", "path", "uri", "target_file")
RAW_CONTENT_KEYS = set(TEXT_KEYS) | {
    "edits",
    "old_string",
    "tool_input",
    "tool_response",
    "structuredPatch",
    "originalFile",
}
SAFE_METADATA_KEYS = {
    "chunk_id",
    "command",
    "cwd",
    "duration_ms",
    "edit_source",
    "event_time",
    "hook_event_name",
    "model",
    "permission_mode",
    "session_id",
    "stop_hook_active",
    "tool_name",
    "tool_use_id",
    "transcript_path",
}


def chunk_from_hook_payload(tool: ToolName, repo: Path, payload: dict[str, Any]) -> AiCodeChunk:
    file_path = _extract_file_path(payload) or "unknown"
    text = _extract_text(payload)
    metadata = {
        key: value
        for key, value in payload.items()
        if key in SAFE_METADATA_KEYS and key not in RAW_CONTENT_KEYS and _json_safe(value)
    }
    metadata["payload_keys"] = sorted(key for key in payload.keys() if key not in RAW_CONTENT_KEYS)

    return AiCodeChunk(
        tool=tool,
        repo_id=str(payload.get("repo_id") or repo_id(repo)),
        commit_base=payload.get("commit_base") or current_head(repo),
        file_path=_normalize_path(file_path, repo),
        event_time=str(payload.get("event_time") or datetime.now(timezone.utc).isoformat()),
        chunk_id=str(payload.get("chunk_id") or uuid.uuid4()),
        line_hashes=hash_lines(text),
        metadata=metadata,
    )


def parse_hook_stdin(stdin_text: str) -> dict[str, Any]:
    stripped = stdin_text.strip()
    if not stripped:
        return {}
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return {"text": stdin_text}
    if isinstance(data, dict):
        return data
    return {"text": json.dumps(data, sort_keys=True)}


def _extract_text(payload: dict[str, Any]) -> str:
    for key in TEXT_KEYS:
        value = payload.get(key)
        if isinstance(value, str):
            return value

    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        value = _first_string(tool_input, TEXT_KEYS)
        if value:
            return value

    tool_response = payload.get("tool_response")
    if isinstance(tool_response, dict):
        value = _first_string(tool_response, TEXT_KEYS)
        if value:
            return value

    edits = payload.get("edits")
    if isinstance(edits, list):
        parts = []
        for edit in edits:
            if isinstance(edit, dict):
                value = _first_string(edit, TEXT_KEYS)
                if value:
                    parts.append(value)
        if parts:
            return "\n".join(parts)
    return ""


def _extract_file_path(payload: dict[str, Any]) -> str | None:
    value = _first_string(payload, FILE_KEYS)
    if value:
        return value
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        value = _first_string(tool_input, FILE_KEYS)
        if value:
            return value
    tool_response = payload.get("tool_response")
    if isinstance(tool_response, dict):
        value = _first_string(tool_response, FILE_KEYS + ("filePath",))
        if value:
            return value
    return None


def _first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _normalize_path(path: str, repo: Path) -> str:
    """Make a file path repo-relative, or return a safe sentinel.

    - Absolute paths must be inside `repo`; otherwise we return "<external>"
      so downstream code (e.g. the dashboard's file reader) can't be tricked
      into accessing arbitrary system files.
    - Relative paths are kept as-is after normalizing separators, with the
      traversal check applied: anything containing `..` segments after
      normalization is rejected.
    """
    if path.startswith("file://"):
        path = path.removeprefix("file://")
    normalized = path.replace("\\", "/").lstrip("/")
    candidate = Path(path.replace("\\", "/"))

    if candidate.is_absolute():
        try:
            resolved = candidate.resolve()
            return resolved.relative_to(repo.resolve()).as_posix()
        except (OSError, ValueError):
            return "<external>"

    # Relative path: reject traversal (..), keep otherwise.
    parts = Path(normalized).parts
    if any(p == ".." for p in parts):
        return "<external>"
    return normalized


def _json_safe(value: Any) -> bool:
    try:
        json.dumps(value)
    except TypeError:
        return False
    return True
