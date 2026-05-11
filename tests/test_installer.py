import json
import shlex
import subprocess

from ai_pr_attribution.installer import install_all, install_hooks


def test_install_hooks_quotes_paths_with_spaces(tmp_path):
    repo = tmp_path / "repo with spaces"
    repo.mkdir()
    created = install_hooks(repo)
    cursor_config = json.loads((repo / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
    command = cursor_config["hooks"]["afterFileEdit"][0]["command"]
    parsed = shlex.split(command)
    assert parsed[-1] == str(repo / ".ai-pr-attribution" / "hooks" / "collect-ai-event.sh")
    assert repo / ".ai-pr-attribution" / "hooks" / "collect-ai-event.sh" in created


def test_install_all_adds_git_pre_commit_hook(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)

    created = install_all(repo)

    pre_commit = repo / ".git" / "hooks" / "pre-commit"
    assert pre_commit in created
    content = pre_commit.read_text(encoding="utf-8")
    assert "ai-pr-attribution managed hook" in content
    assert ".ai-pr-attribution/hooks/import-codex-session.sh" in content


def test_install_all_preserves_existing_pre_commit_hook(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    pre_commit = repo / ".git" / "hooks" / "pre-commit"
    pre_commit.write_text("#!/usr/bin/env sh\necho existing\n", encoding="utf-8")

    install_all(repo)

    backup = repo / ".git" / "hooks" / "pre-commit.before-ai-pr-attribution"
    assert backup.exists()
    assert "echo existing" in backup.read_text(encoding="utf-8")
    assert "pre-commit.before-ai-pr-attribution" in pre_commit.read_text(encoding="utf-8")
