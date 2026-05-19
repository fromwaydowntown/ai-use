"""Tests for github.py PR comment + check run upsert (mocked HTTP)."""
import json
from unittest.mock import patch

from ai_use.github import CHECK_RUN_NAME, upsert_check_run, upsert_pr_comment


def _event_file(tmp_path, pr_number=42):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": pr_number}}))
    return event


# ── PR comment upsert ────────────────────────────────────────────────────────

def test_upsert_comment_creates_new_when_none_exists(tmp_path, monkeypatch):
    event = _event_file(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))

    calls = []

    def fake(method, url, headers, data=None):
        calls.append((method, url, data))
        return [] if method == "GET" else {}

    with patch("ai_use.github._request", side_effect=fake):
        upsert_pr_comment("test body")

    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"
    assert "owner/repo/issues/42/comments" in calls[1][1]


def test_upsert_comment_patches_existing(tmp_path, monkeypatch):
    event = _event_file(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))

    existing_url = "https://api.github.com/comments/777"
    calls = []

    def fake(method, url, headers, data=None):
        calls.append((method, url))
        if method == "GET":
            return [
                {"body": "unrelated", "url": "x"},
                {"body": "<!-- ai-use:mvp -->\nold", "url": existing_url},
            ]
        return {}

    with patch("ai_use.github._request", side_effect=fake):
        upsert_pr_comment("new body")

    assert calls[1] == ("PATCH", existing_url)


# ── Check Run upsert ─────────────────────────────────────────────────────────

def test_upsert_check_run_creates_new_when_none_exists(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    calls = []

    def fake(method, url, headers, data=None):
        calls.append((method, url, data))
        if method == "GET":
            return {"check_runs": []}
        return {}

    with patch("ai_use.github._request", side_effect=fake):
        upsert_check_run("abc123", "61% AI", "## body")

    assert calls[0][0] == "GET"
    assert "abc123/check-runs" in calls[0][1]
    assert calls[1][0] == "POST"
    assert "/check-runs" in calls[1][1] and "owner/repo" in calls[1][1]

    body = json.loads(calls[1][2])
    assert body["name"] == CHECK_RUN_NAME
    assert body["head_sha"] == "abc123"
    assert body["status"] == "completed"
    assert body["conclusion"] == "neutral"
    assert body["output"]["title"] == "61% AI"
    assert body["output"]["summary"] == "## body"


def test_upsert_check_run_patches_existing(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    calls = []

    def fake(method, url, headers, data=None):
        calls.append((method, url))
        if method == "GET":
            return {"check_runs": [{"id": 999}]}
        return {}

    with patch("ai_use.github._request", side_effect=fake):
        upsert_check_run("abc123", "updated", "## body")

    assert calls[1] == ("PATCH", "https://api.github.com/repos/owner/repo/check-runs/999")


def test_upsert_check_run_filters_by_name(monkeypatch):
    """GET should filter by check_name so unrelated runs on the same SHA are ignored."""
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    captured_url = []

    def fake(method, url, headers, data=None):
        if method == "GET":
            captured_url.append(url)
            return {"check_runs": []}
        return {}

    with patch("ai_use.github._request", side_effect=fake):
        upsert_check_run("sha1", "t", "s")

    assert "check_name=AI+Attribution" in captured_url[0]
