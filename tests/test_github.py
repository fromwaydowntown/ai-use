"""Tests for github.py PR comment upsert (mocked HTTP)."""
import json
from unittest.mock import patch

from ai_pr_attribution.github import upsert_pr_comment


def _event_file(tmp_path, pr_number=42):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": pr_number}}))
    return event


def test_upsert_creates_new_comment_when_none_exists(tmp_path, monkeypatch):
    event = _event_file(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))

    calls = []

    def fake_request(method, url, headers, data=None):
        calls.append((method, url, data))
        if method == "GET":
            return []  # no existing comments
        return {}

    with patch("ai_pr_attribution.github._request", side_effect=fake_request):
        upsert_pr_comment("test body")

    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"
    assert "owner/repo/issues/42/comments" in calls[1][1]
    assert b"test body" in calls[1][2]


def test_upsert_patches_existing_comment(tmp_path, monkeypatch):
    event = _event_file(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))

    calls = []
    existing_url = "https://api.github.com/comments/777"

    def fake_request(method, url, headers, data=None):
        calls.append((method, url))
        if method == "GET":
            return [
                {"body": "unrelated comment", "url": "x"},
                {"body": "<!-- ai-pr-attribution:mvp -->\nold", "url": existing_url},
            ]
        return {}

    with patch("ai_pr_attribution.github._request", side_effect=fake_request):
        upsert_pr_comment("new body")

    assert calls[1] == ("PATCH", existing_url)
