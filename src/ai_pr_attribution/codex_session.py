from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from ai_pr_attribution.events import append_chunk, read_chunks
from ai_pr_attribution.git_utils import current_head, repo_id
from ai_pr_attribution.hashing import hash_lines
from ai_pr_attribution.schema import AiCodeChunk


def latest_codex_session(home: Path | None = None) -> Path | None:
    root = (home or Path.home()) / ".codex" / "sessions"
    if not root.exists():
        return None
    sessions = [path for path in root.rglob("*.jsonl") if path.is_file()]
    if not sessions:
        return None
    return max(sessions, key=lambda path: path.stat().st_mtime)


def import_codex_session(session_file: Path, repo: Path, events_file: Path) -> int:
    existing_ids = {chunk.chunk_id for chunk in read_chunks(events_file)}
    imported = 0
    for chunk in chunks_from_codex_session(session_file, repo):
        if chunk.chunk_id in existing_ids:
            continue
        append_chunk(events_file, chunk)
        existing_ids.add(chunk.chunk_id)
        imported += 1
    return imported


def chunks_from_codex_session(session_file: Path, repo: Path) -> list[AiCodeChunk]:
    chunks: list[AiCodeChunk] = []
    repo = repo.resolve()
    with session_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            chunks.extend(_chunks_from_event(event, session_file, repo))
    return chunks


def _chunks_from_event(event: dict[str, Any], session_file: Path, repo: Path) -> list[AiCodeChunk]:
    payload = event.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "patch_apply_end":
        return []
    changes = payload.get("changes")
    if not isinstance(changes, dict):
        return []

    chunks: list[AiCodeChunk] = []
    for raw_path, change in changes.items():
        if not isinstance(change, dict):
            continue
        diff = change.get("unified_diff")
        if not isinstance(diff, str):
            continue
        added_text = "\n".join(_added_lines_from_fragment(diff))
        if not added_text:
            continue
        file_path = _repo_relative_path(raw_path, repo)
        if file_path is None:
            continue
        chunks.append(
            AiCodeChunk(
                tool="codex",
                repo_id=repo_id(repo),
                commit_base=current_head(repo),
                file_path=file_path,
                event_time=str(event.get("timestamp") or ""),
                chunk_id=_stable_chunk_id(session_file, payload, file_path, diff),
                line_hashes=hash_lines(added_text),
                metadata={
                    "source": "codex_session_import",
                    "session_file": str(session_file),
                    "call_id": payload.get("call_id"),
                    "turn_id": payload.get("turn_id"),
                    "change_type": change.get("type"),
                },
            )
        )
    return chunks


def _added_lines_from_fragment(diff: str) -> list[str]:
    lines: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            lines.append(line[1:])
    return lines


def _repo_relative_path(raw_path: str, repo: Path) -> str | None:
    path = Path(raw_path)
    try:
        return path.resolve().relative_to(repo).as_posix()
    except (OSError, ValueError):
        return None


def _stable_chunk_id(session_file: Path, payload: dict[str, Any], file_path: str, diff: str) -> str:
    basis = f"{session_file}:{payload.get('call_id')}:{file_path}:{diff}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, basis))
