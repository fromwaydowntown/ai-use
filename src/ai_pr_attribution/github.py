from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ai_pr_attribution.report import COMMENT_MARKER


def upsert_pr_comment(body: str) -> None:
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    event_path = os.environ["GITHUB_EVENT_PATH"]

    with open(event_path, "r", encoding="utf-8") as handle:
        event = json.load(handle)
    pr_number = event["pull_request"]["number"]

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    comments_url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    comments = _request("GET", comments_url, headers)
    existing = next((comment for comment in comments if COMMENT_MARKER in comment.get("body", "")), None)
    payload = json.dumps({"body": body}).encode("utf-8")

    if existing:
        _request("PATCH", existing["url"], headers, payload)
    else:
        _request("POST", comments_url, headers, payload)


def _request(method: str, url: str, headers: dict[str, str], data: bytes | None = None):
    request = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {url} failed: {exc.code} {detail}") from exc
    if not body:
        return None
    return json.loads(body)
