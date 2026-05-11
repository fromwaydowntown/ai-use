from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ai_pr_attribution.schema import AiCodeChunk


DEFAULT_EVENTS_PATH = Path(".ai-pr-attribution/events.ndjson")


def append_chunk(path: Path, chunk: AiCodeChunk) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(chunk.to_json(), sort_keys=True) + "\n")


def read_chunks(path: Path) -> list[AiCodeChunk]:
    if not path.exists():
        return []
    chunks: list[AiCodeChunk] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(AiCodeChunk.from_json(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                raise ValueError(f"invalid event at {path}:{lineno}: {exc}") from exc
    return chunks


def write_chunks(path: Path, chunks: Iterable[AiCodeChunk]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk.to_json(), sort_keys=True) + "\n")
