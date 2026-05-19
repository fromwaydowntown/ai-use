#!/usr/bin/env sh
repo="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ -x "$repo/.venv/bin/python" ]; then
  py="$repo/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  py="python3"
else
  py="python"
fi
"$py" -m ai_use.cli import-codex-session --repo "$repo" >/dev/null 2>&1 || true
