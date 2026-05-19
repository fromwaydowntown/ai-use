from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from ai_use.config import collector_token, collector_url
from ai_use.events import read_chunks, write_chunks
from ai_use.git_utils import current_head, repo_id, run_git
from ai_use.schema import AiCodeChunk


def upload_telemetry(repo: Path, events_file: Path, url: str | None = None, token: str | None = None) -> dict:
    repo = repo.resolve()
    target_url = url or collector_url(repo)
    if not target_url:
        raise ValueError("collector URL is not configured")
    payload = {
        "repo_id": repo_id(repo),
        "branch": run_git(repo, ["branch", "--show-current"]),
        "commit_sha": current_head(repo),
        "chunks": [chunk.to_json() for chunk in read_chunks(events_file)],
    }
    return _json_request("POST", _join_url(target_url, "/v1/telemetry"), payload, token or collector_token(repo))


def fetch_telemetry(
    repo: Path,
    output_file: Path,
    url: str | None = None,
    token: str | None = None,
    repo_value: str | None = None,
    commit_sha: str | None = None,
) -> list[AiCodeChunk]:
    repo = repo.resolve()
    target_url = url or collector_url(repo)
    if not target_url:
        raise ValueError("collector URL is not configured")
    query = urllib.parse.urlencode(
        {
            "repo_id": repo_value or repo_id(repo),
            "commit_sha": commit_sha or current_head(repo) or "",
        }
    )
    data = _json_request("GET", f"{_join_url(target_url, '/v1/telemetry')}?{query}", None, token or collector_token(repo))
    chunks = [AiCodeChunk.from_json(chunk) for chunk in data.get("chunks", [])]
    write_chunks(output_file, chunks)
    return chunks


def _json_request(method: str, url: str, payload: dict | None, token: str | None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, method=method, headers=headers, data=body)
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8")
    return json.loads(text) if text else {}


def _join_url(base: str, path: str) -> str:
    return base.rstrip("/") + path
