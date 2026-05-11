from __future__ import annotations

import argparse
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def serve(host: str, port: int, db_path: Path, token: str | None = None) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _init_db(db_path)

    class Handler(CollectorHandler):
        database_path = db_path
        bearer_token = token

    ThreadingHTTPServer((host, port), Handler).serve_forever()


class CollectorHandler(BaseHTTPRequestHandler):
    database_path: Path
    bearer_token: str | None = None

    def do_GET(self) -> None:
        if not self._authorized():
            self._send(401, {"error": "unauthorized"})
            return
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._send(200, {"ok": True})
            return
        if parsed.path != "/v1/telemetry":
            self._send(404, {"error": "not found"})
            return
        query = parse_qs(parsed.query)
        repo_id = _single(query, "repo_id")
        commit_sha = _single(query, "commit_sha")
        if not repo_id or not commit_sha:
            self._send(400, {"error": "repo_id and commit_sha are required"})
            return
        self._send(200, {"chunks": _fetch_chunks(self.database_path, repo_id, commit_sha)})

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(401, {"error": "unauthorized"})
            return
        if urlparse(self.path).path != "/v1/telemetry":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid json"})
            return
        required = ("repo_id", "commit_sha", "chunks")
        if any(not payload.get(key) for key in required):
            self._send(400, {"error": "repo_id, commit_sha, and chunks are required"})
            return
        stored = _store_chunks(
            self.database_path,
            str(payload["repo_id"]),
            str(payload.get("branch") or ""),
            str(payload["commit_sha"]),
            payload["chunks"],
        )
        self._send(200, {"stored_chunks": stored})

    def log_message(self, format: str, *args) -> None:
        return

    def _authorized(self) -> bool:
        if not self.bearer_token:
            return True
        return self.headers.get("Authorization") == f"Bearer {self.bearer_token}"

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _init_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                repo_id TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                branch TEXT,
                chunk_id TEXT NOT NULL,
                chunk_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (repo_id, commit_sha, chunk_id)
            )
            """
        )


def _store_chunks(path: Path, repo_id: str, branch: str, commit_sha: str, chunks: list[dict]) -> int:
    with sqlite3.connect(path) as conn:
        stored = 0
        for chunk in chunks:
            chunk_id = str(chunk.get("chunk_id") or "")
            if not chunk_id:
                continue
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO chunks(repo_id, commit_sha, branch, chunk_id, chunk_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (repo_id, commit_sha, branch, chunk_id, json.dumps(chunk, sort_keys=True)),
            )
            stored += cursor.rowcount
        return stored


def _fetch_chunks(path: Path, repo_id: str, commit_sha: str) -> list[dict]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT chunk_json FROM chunks WHERE repo_id = ? AND commit_sha = ? ORDER BY created_at, chunk_id",
            (repo_id, commit_sha),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def _single(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key) or []
    return values[0] if values else None
