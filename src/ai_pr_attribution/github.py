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


CHECK_RUN_NAME = "AI Attribution"


def upsert_check_run(head_sha: str, title: str, summary: str) -> None:
    """Create or update a Check Run with the attribution result.

    Check Runs appear at the bottom of PRs alongside CI checks, with a
    dedicated Summary tab for rich markdown.
    """
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    existing = _find_existing_check_run(repo, head_sha, headers)
    body = {
        "name": CHECK_RUN_NAME,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": "neutral",
        "output": {"title": title, "summary": summary},
    }
    payload = json.dumps(body).encode("utf-8")

    if existing:
        url = f"https://api.github.com/repos/{repo}/check-runs/{existing['id']}"
        _request("PATCH", url, headers, payload)
    else:
        url = f"https://api.github.com/repos/{repo}/check-runs"
        _request("POST", url, headers, payload)


def _find_existing_check_run(repo: str, head_sha: str, headers: dict[str, str]) -> dict | None:
    url = f"https://api.github.com/repos/{repo}/commits/{head_sha}/check-runs?check_name={CHECK_RUN_NAME.replace(' ', '+')}"
    response = _request("GET", url, headers)
    if not response:
        return None
    runs = response.get("check_runs", [])
    return runs[0] if runs else None


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
