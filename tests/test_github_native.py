"""Tests for github_native: storing events as git blobs and pushing/pulling refs."""
import subprocess

from ai_use.github_native import _user_ref, download_events, upload_events


def init_repo(path, with_remote=None):
    path.mkdir(exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    if with_remote is not None:
        subprocess.run(["git", "remote", "add", "origin", str(with_remote)], cwd=path, check=True)
    return path


def init_bare_remote(path):
    path.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "--bare"], cwd=path, check=True, capture_output=True)
    return path


def test_user_ref_is_stable_per_email(tmp_path):
    repo = init_repo(tmp_path / "repo")
    ref1 = _user_ref(repo)
    ref2 = _user_ref(repo)
    assert ref1 == ref2
    assert ref1.startswith("refs/ai-attribution/")


def test_user_ref_differs_per_email(tmp_path):
    repo_a = init_repo(tmp_path / "a")
    repo_b = init_repo(tmp_path / "b")
    subprocess.run(["git", "config", "user.email", "other@example.com"], cwd=repo_b, check=True)
    assert _user_ref(repo_a) != _user_ref(repo_b)


def test_upload_events_skips_empty_file(tmp_path):
    repo = init_repo(tmp_path / "repo")
    events = tmp_path / "events.ndjson"
    events.write_text("")
    assert upload_events(events, repo) == 0


def test_upload_events_skips_missing_file(tmp_path):
    repo = init_repo(tmp_path / "repo")
    assert upload_events(tmp_path / "nonexistent.ndjson", repo) == 0


def test_upload_and_download_roundtrip(tmp_path):
    remote = init_bare_remote(tmp_path / "remote.git")
    repo = init_repo(tmp_path / "repo", with_remote=remote)

    # Need at least one commit on the repo before pushing
    (repo / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    events_file = repo / "events.ndjson"
    events_file.write_text('{"chunk_id":"x","tool":"cursor"}\n{"chunk_id":"y","tool":"codex"}\n')
    uploaded = upload_events(events_file, repo)
    assert uploaded > 0

    # Clone to a second repo and download
    other = tmp_path / "consumer"
    subprocess.run(["git", "clone", str(remote), str(other)], check=True, capture_output=True)
    output = other / "fetched.ndjson"
    count = download_events(output, other)
    assert count > 0
    content = output.read_text()
    assert '"chunk_id":"x"' in content
    assert '"chunk_id":"y"' in content


def test_download_returns_zero_when_no_refs(tmp_path):
    remote = init_bare_remote(tmp_path / "remote.git")
    repo = init_repo(tmp_path / "repo", with_remote=remote)
    output = tmp_path / "fetched.ndjson"
    assert download_events(output, repo) == 0
