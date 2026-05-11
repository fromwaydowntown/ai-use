#!/usr/bin/env sh
tool="${AI_PR_ATTRIBUTION_TOOL:-cursor}"
repo="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ -x "$repo/.venv/bin/ai-pr-attribution" ]; then
  cli="$repo/.venv/bin/ai-pr-attribution"
else
  cli="ai-pr-attribution"
fi
exec "$cli" collect-hook --tool "$tool" --repo "$repo"
