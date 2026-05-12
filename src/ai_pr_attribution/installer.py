from __future__ import annotations

import importlib.resources
import json
import shlex
import stat
from pathlib import Path

from ai_pr_attribution.config import write_config

HOOK_MARKER = "# ai-pr-attribution managed hook"

HOOK_SCRIPT = """#!/usr/bin/env sh
tool="${AI_PR_ATTRIBUTION_TOOL:-cursor}"
repo="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ -x "$repo/.venv/bin/python" ]; then
  py="$repo/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  py="python3"
else
  py="python"
fi
exec "$py" -m ai_pr_attribution.cli collect-hook --tool "$tool" --repo "$repo"
"""

CODEX_IMPORT_SCRIPT = """#!/usr/bin/env sh
repo="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ -x "$repo/.venv/bin/python" ]; then
  py="$repo/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  py="python3"
else
  py="python"
fi
"$py" -m ai_pr_attribution.cli import-codex-session --repo "$repo" >/dev/null 2>&1 || true
"""

UPLOAD_SCRIPT = """#!/usr/bin/env sh
repo="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ -x "$repo/.venv/bin/ai-pr-attribution" ]; then
  cli="$repo/.venv/bin/ai-pr-attribution"
else
  cli="ai-pr-attribution"
fi
"$cli" import-codex-session --repo "$repo" >/dev/null 2>&1 || true
"$cli" upload-telemetry --repo "$repo" >/dev/null 2>&1 || true
"""

GITHUB_NATIVE_UPLOAD_SCRIPT = """#!/usr/bin/env sh
# Guard against recursive invocation when git push is called inside this hook
if [ "${AI_PR_ATTRIBUTION_UPLOADING:-0}" = "1" ]; then
  exit 0
fi
export AI_PR_ATTRIBUTION_UPLOADING=1
repo="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ -x "$repo/.venv/bin/python" ]; then
  py="$repo/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  py="python3"
else
  py="python"
fi
"$py" -m ai_pr_attribution.cli import-codex-session --repo "$repo" >/dev/null 2>&1 || true
"$py" -m ai_pr_attribution.cli upload-ref --repo "$repo" >/dev/null 2>&1 || true
"""


def install_hooks(repo: Path, collector_url: str | None = None, collector_token: str | None = None) -> list[Path]:
    repo = repo.resolve()
    created: list[Path] = []
    if collector_url or collector_token:
        created.append(write_config(repo, {"collector_url": collector_url, "collector_token": collector_token}))

    hook_dir = repo / ".ai-pr-attribution" / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)

    runner = hook_dir / "collect-ai-event.sh"
    runner.write_text(HOOK_SCRIPT, encoding="utf-8")
    runner.chmod(runner.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    created.append(runner)

    codex_importer = hook_dir / "import-codex-session.sh"
    codex_importer.write_text(CODEX_IMPORT_SCRIPT, encoding="utf-8")
    codex_importer.chmod(codex_importer.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    created.append(codex_importer)

    uploader = hook_dir / "upload-telemetry.sh"
    uploader.write_text(UPLOAD_SCRIPT, encoding="utf-8")
    uploader.chmod(uploader.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    created.append(uploader)

    cursor_config = repo / ".cursor" / "hooks.json"
    cursor_config.parent.mkdir(parents=True, exist_ok=True)
    cursor_config.write_text(json.dumps(_cursor_hooks_config(runner), indent=2) + "\n", encoding="utf-8")
    created.append(cursor_config)

    claude_config = repo / ".claude" / "settings.json"
    claude_config.parent.mkdir(parents=True, exist_ok=True)
    claude_config.write_text(json.dumps(_claude_hooks_config(runner), indent=2) + "\n", encoding="utf-8")
    created.append(claude_config)

    codex_readme = repo / ".ai-pr-attribution" / "codex-hook.md"
    codex_readme.write_text(_codex_instructions(runner), encoding="utf-8")
    created.append(codex_readme)

    gitignore = repo / ".ai-pr-attribution" / ".gitignore"
    gitignore.write_text("events.ndjson\nfetched-events.ndjson\ncollector.sqlite3*\nconfig.json\n*.tmp\n", encoding="utf-8")
    created.append(gitignore)

    for git_hook in _install_git_hooks(repo, codex_importer, uploader):
        created.append(git_hook)
    return created


def install_all(repo: Path, collector_url: str | None = None, collector_token: str | None = None) -> list[Path]:
    return install_hooks(repo, collector_url=collector_url, collector_token=collector_token)


def install_github_native(repo: Path) -> list[Path]:
    """Install hooks that upload events to refs/ai-attribution/<user> via git push.

    No secrets or external services required — uses normal git push credentials.
    """
    repo = repo.resolve()
    created: list[Path] = []

    hook_dir = repo / ".ai-pr-attribution" / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)

    runner = hook_dir / "collect-ai-event.sh"
    runner.write_text(HOOK_SCRIPT, encoding="utf-8")
    runner.chmod(runner.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    created.append(runner)

    codex_importer = hook_dir / "import-codex-session.sh"
    codex_importer.write_text(CODEX_IMPORT_SCRIPT, encoding="utf-8")
    codex_importer.chmod(codex_importer.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    created.append(codex_importer)

    uploader = hook_dir / "upload-ref.sh"
    uploader.write_text(GITHUB_NATIVE_UPLOAD_SCRIPT, encoding="utf-8")
    uploader.chmod(uploader.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    created.append(uploader)

    cursor_config = repo / ".cursor" / "hooks.json"
    cursor_config.parent.mkdir(parents=True, exist_ok=True)
    cursor_config.write_text(
        json.dumps(_cursor_hooks_config(runner), indent=2) + "\n", encoding="utf-8"
    )
    created.append(cursor_config)

    claude_config = repo / ".claude" / "settings.json"
    claude_config.parent.mkdir(parents=True, exist_ok=True)
    claude_config.write_text(
        json.dumps(_claude_hooks_config(runner), indent=2) + "\n", encoding="utf-8"
    )
    created.append(claude_config)

    gitignore = repo / ".ai-pr-attribution" / ".gitignore"
    gitignore.write_text(
        "events.ndjson\nfetched-events.ndjson\ncollector.sqlite3*\nconfig.json\n*.tmp\n",
        encoding="utf-8",
    )
    created.append(gitignore)

    for git_hook in _install_git_hooks(repo, codex_importer, uploader):
        created.append(git_hook)

    workflow_dest = _install_workflow(repo)
    created.append(workflow_dest)

    return created


def _install_workflow(repo: Path) -> Path:
    workflow_dir = repo / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    dest = workflow_dir / "ai-pr-attribution.yml"
    pkg = importlib.resources.files("ai_pr_attribution") / "data" / "workflow.yml"
    dest.write_bytes(pkg.read_bytes())
    return dest


def _cursor_hooks_config(runner: Path) -> dict:
    rel = runner.name  # always collect-ai-event.sh
    command = f'AI_PR_ATTRIBUTION_TOOL=cursor sh "$(git rev-parse --show-toplevel)/.ai-pr-attribution/hooks/{rel}"'
    return {
        "version": 1,
        "hooks": {
            name: [{"command": command}]
            for name in [
                "sessionStart",
                "beforeSubmitPrompt",
                "afterFileEdit",
                "afterTabFileEdit",
                "postToolUse",
                "beforeShellExecution",
                "afterShellExecution",
                "beforeMCPExecution",
                "afterMCPExecution",
                "stop",
            ]
        },
    }


def _claude_hooks_config(runner: Path) -> dict:
    rel = runner.name  # always collect-ai-event.sh
    command = f'AI_PR_ATTRIBUTION_TOOL=claude_code sh "$(git rev-parse --show-toplevel)/.ai-pr-attribution/hooks/{rel}"'
    return {
        "hooks": {
            "PostToolUse": [{"matcher": "Edit|MultiEdit|Write", "hooks": [{"type": "command", "command": command}]}],
            "Stop": [{"hooks": [{"type": "command", "command": command}]}],
        }
    }


def _codex_instructions(runner: Path) -> str:
    rel = f'.ai-pr-attribution/hooks/{runner.name}'
    return f"""# Codex Hook Adapter

Codex Desktop does not currently expose the same repo hook file shape as Cursor
or Claude Code. The installer adds a Git `pre-commit` hook that imports local
Codex session patch events before each commit.

Manual collection is also available (run from repo root):

```bash
AI_PR_ATTRIBUTION_TOOL=codex sh {shlex.quote(rel)}
```

The collector stores hash-only evidence in `.ai-pr-attribution/events.ndjson`.
"""


def _install_git_hooks(repo: Path, codex_importer: Path, uploader: Path) -> list[Path]:
    git_dir = repo / ".git"
    if not git_dir.exists():
        return []

    # In a git worktree, .git is a file containing "gitdir: <path>"
    if git_dir.is_file():
        line = git_dir.read_text(encoding="utf-8").strip()
        if line.startswith("gitdir:"):
            real_git = Path(line[len("gitdir:"):].strip())
            if not real_git.is_absolute():
                real_git = (repo / real_git).resolve()
            # Hooks live in the common dir (main repo's .git), not the worktree's gitdir
            common = real_git / "commondir"
            if common.exists():
                common_path = common.read_text(encoding="utf-8").strip()
                git_dir = (real_git / common_path).resolve()
            else:
                git_dir = real_git

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    return [
        _install_git_hook(hooks_dir / "pre-commit", codex_importer),
        _install_git_hook(hooks_dir / "pre-push", uploader),
    ]


def _install_git_hook(hook_path: Path, command_path: Path) -> Path:
    backup = hook_path.with_name(f"{hook_path.name}.before-ai-pr-attribution")
    existing = hook_path.read_text(encoding="utf-8") if hook_path.exists() else ""
    if HOOK_MARKER in existing:
        preserved_call = f'{shlex.quote(str(backup))} "$@"'
    elif existing.strip():
        if not backup.exists():
            backup.write_text(existing, encoding="utf-8")
            backup.chmod(backup.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        preserved_call = f'{shlex.quote(str(backup))} "$@"'
    else:
        preserved_call = ""

    hook_path.write_text(_git_hook_script(command_path, preserved_call), encoding="utf-8")
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook_path


def _git_hook_script(command_path: Path, preserved_call: str) -> str:
    preserved = ""
    if preserved_call:
        preserved = f'\n{preserved_call}\n'
    return f"""#!/usr/bin/env sh
{HOOK_MARKER}
{shlex.quote(str(command_path))} || true
{preserved}"""
