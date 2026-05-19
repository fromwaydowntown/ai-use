from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ToolName = Literal["cursor", "claude_code", "codex"]
Confidence = Literal["exact_file_match", "cross_file_match", "unmatched"]


@dataclass(frozen=True)
class AiCodeChunk:
    tool: ToolName
    repo_id: str
    commit_base: str | None
    file_path: str
    event_time: str
    chunk_id: str
    line_hashes: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "tool": self.tool,
            "repo_id": self.repo_id,
            "commit_base": self.commit_base,
            "file_path": self.file_path,
            "event_time": self.event_time,
            "chunk_id": self.chunk_id,
            "line_hashes": list(self.line_hashes),
            "metadata": self.metadata,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "AiCodeChunk":
        tool = data["tool"]
        if tool not in {"cursor", "claude_code", "codex"}:
            raise ValueError(f"unsupported tool: {tool}")
        return cls(
            tool=tool,
            repo_id=str(data["repo_id"]),
            commit_base=data.get("commit_base"),
            file_path=str(data["file_path"]),
            event_time=str(data["event_time"]),
            chunk_id=str(data["chunk_id"]),
            line_hashes=tuple(str(value) for value in data.get("line_hashes", [])),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(frozen=True)
class AddedLine:
    file_path: str
    new_lineno: int
    text: str
    line_hash: str


@dataclass(frozen=True)
class LineAttribution:
    line: AddedLine
    confidence: Confidence
    chunk_id: str | None = None
    tool: ToolName | None = None


@dataclass(frozen=True)
class AttributionSummary:
    total_added_lines: int
    exact_file_match: int
    cross_file_match: int
    unmatched: int
    by_tool: dict[str, int]

    @property
    def attributed_lines(self) -> int:
        return self.exact_file_match + self.cross_file_match

    @property
    def attribution_percent(self) -> float:
        if self.total_added_lines == 0:
            return 0.0
        return round((self.attributed_lines / self.total_added_lines) * 100, 2)
