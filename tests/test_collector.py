import json
import subprocess
import threading
import urllib.request

from ai_use.collector_server import serve
from ai_use.events import read_chunks, write_chunks
from ai_use.schema import AiCodeChunk
from ai_use.telemetry_client import fetch_telemetry, upload_telemetry


def test_collector_upload_and_fetch_round_trip(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    events = repo / ".ai-use" / "events.ndjson"
    output = repo / ".ai-use" / "fetched.ndjson"
    write_chunks(
        events,
        [
            AiCodeChunk(
                tool="cursor",
                repo_id=str(repo),
                commit_base="base",
                file_path="app.py",
                event_time="2026-05-11T00:00:00Z",
                chunk_id="chunk-1",
                line_hashes=("abc",),
            )
        ],
    )

    db = tmp_path / "collector.sqlite3"
    port = _free_port()
    thread = threading.Thread(target=serve, args=("127.0.0.1", port, db, None), daemon=True)
    thread.start()
    _wait_for_health(port)

    result = upload_telemetry(repo, events, url=f"http://127.0.0.1:{port}")
    assert result["stored_chunks"] == 1
    chunks = fetch_telemetry(repo, output, url=f"http://127.0.0.1:{port}")
    assert len(chunks) == 1

    # Also verify explicit SHA lookup, which is what GitHub Actions uses.
    payload = {
        "repo_id": str(repo),
        "commit_sha": "head-sha",
        "branch": "feature",
        "chunks": [read_chunks(events)[0].to_json()],
    }
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/telemetry",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload).encode(),
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert json.loads(response.read())["stored_chunks"] == 1

    fetched = fetch_telemetry(repo, output, url=f"http://127.0.0.1:{port}", repo_value=str(repo), commit_sha="head-sha")
    assert len(fetched) == 1
    assert fetched[0].chunk_id == "chunk-1"
    assert read_chunks(output)[0].tool == "cursor"


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_health(port: int) -> None:
    import time

    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=0.2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("collector did not start")
