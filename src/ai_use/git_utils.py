from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(repo: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def repo_id(repo: Path) -> str:
    remote = run_git(repo, ["config", "--get", "remote.origin.url"])
    if remote:
        return remote
    root = run_git(repo, ["rev-parse", "--show-toplevel"])
    return root or str(repo.resolve())


def current_head(repo: Path) -> str | None:
    return run_git(repo, ["rev-parse", "HEAD"])
