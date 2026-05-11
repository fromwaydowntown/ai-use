#!/usr/bin/env sh
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
