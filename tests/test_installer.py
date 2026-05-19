import json
import os
import shlex
import subprocess

from ai_use.installer import install_all, install_github_native, install_hooks


def test_install_hooks_quotes_paths_with_spaces(tmp_path):
    repo = tmp_path / "repo with spaces"
    repo.mkdir()
    created = install_hooks(repo)
    cursor_config = json.loads((repo / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
    command = cursor_config["hooks"]["afterFileEdit"][0]["command"]
    assert ".ai-use/hooks/collect-ai-event.sh" in command
    assert repo / ".ai-use" / "hooks" / "collect-ai-event.sh" in created


def test_install_all_adds_git_pre_commit_hook(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)

    created = install_all(repo)

    pre_commit = repo / ".git" / "hooks" / "pre-commit"
    assert pre_commit in created
    content = pre_commit.read_text(encoding="utf-8")
    assert "ai-use managed hook" in content
    assert ".ai-use/hooks/import-codex-session.sh" in content


def test_install_all_preserves_existing_pre_commit_hook(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    pre_commit = repo / ".git" / "hooks" / "pre-commit"
    pre_commit.write_text("#!/usr/bin/env sh\necho existing\n", encoding="utf-8")

    install_all(repo)

    backup = repo / ".git" / "hooks" / "pre-commit.before-ai-use"
    assert backup.exists()
    assert "echo existing" in backup.read_text(encoding="utf-8")
    assert "pre-commit.before-ai-use" in pre_commit.read_text(encoding="utf-8")


# ── github-native install (the default rollout path) ─────────────────────────

def test_install_github_native_creates_all_expected_files(tmp_path):
    """The github-native install (default on rollout) must produce:
    - hook runner scripts (collect, codex-import, upload-ref)
    - Cursor and Claude Code hook configs
    - both workflow YAMLs (attribution + dashboard)
    - git pre-commit and pre-push hooks
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    created = install_github_native(repo)

    must_exist = [
        repo / ".ai-use" / "hooks" / "collect-ai-event.sh",
        repo / ".ai-use" / "hooks" / "import-codex-session.sh",
        repo / ".ai-use" / "hooks" / "upload-ref.sh",
        repo / ".cursor" / "hooks.json",
        repo / ".claude" / "settings.json",
        repo / ".github" / "workflows" / "ai-use.yml",
        repo / ".github" / "workflows" / "ai-use-dashboard.yml",
        repo / ".git" / "hooks" / "pre-commit",
        repo / ".git" / "hooks" / "pre-push",
    ]
    for path in must_exist:
        assert path.exists(), f"missing: {path}"
        assert path in created, f"not in created list: {path}"


def test_pre_push_hook_has_recursion_guard(tmp_path):
    """The pre-push hook calls `git push` to upload events, which would
    re-trigger pre-push infinitely. AI_PR_ATTRIBUTION_UPLOADING=1 must be
    set during the inner push so the guard short-circuits.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    install_github_native(repo)

    uploader = repo / ".ai-use" / "hooks" / "upload-ref.sh"
    content = uploader.read_text()
    assert 'AI_PR_ATTRIBUTION_UPLOADING' in content
    assert 'export AI_PR_ATTRIBUTION_UPLOADING=1' in content


def test_upload_ref_script_exits_zero_when_guard_set(tmp_path):
    """When AI_PR_ATTRIBUTION_UPLOADING=1 is in the env, the upload script
    must exit 0 immediately without doing any work."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    install_github_native(repo)
    uploader = repo / ".ai-use" / "hooks" / "upload-ref.sh"

    result = subprocess.run(
        ["sh", str(uploader)],
        cwd=repo,
        env={**os.environ, "AI_PR_ATTRIBUTION_UPLOADING": "1"},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"recursion guard failed: {result.stderr}"


def test_github_native_workflow_files_have_correct_permissions(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    install_github_native(repo)

    attribution_yml = (repo / ".github" / "workflows" / "ai-use.yml").read_text()
    assert "checks: write" in attribution_yml
    # must NOT request pull-requests:write (security minimum)
    assert "pull-requests: write" not in attribution_yml

    dashboard_yml = (repo / ".github" / "workflows" / "ai-use-dashboard.yml").read_text()
    assert "contents: write" in dashboard_yml
