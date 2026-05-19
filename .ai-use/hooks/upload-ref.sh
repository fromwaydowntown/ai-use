#!/usr/bin/env sh
# Guard against recursive invocation when git push is called inside this hook
if [ "${AI_USE_UPLOADING:-0}" = "1" ]; then
  exit 0
fi
export AI_USE_UPLOADING=1
repo="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ -x "$repo/.venv/bin/python" ]; then
  py="$repo/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  py="python3"
else
  py="python"
fi
"$py" -m ai_use.cli import-codex-session --repo "$repo" >/dev/null 2>&1 || true
"$py" -m ai_use.cli upload-ref --repo "$repo" >/dev/null 2>&1 || true
