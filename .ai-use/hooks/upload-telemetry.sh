#!/usr/bin/env sh
repo="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ -x "$repo/.venv/bin/ai-use" ]; then
  cli="$repo/.venv/bin/ai-use"
else
  cli="ai-use"
fi
"$cli" import-codex-session --repo "$repo" >/dev/null 2>&1 || true
"$cli" upload-telemetry --repo "$repo" >/dev/null 2>&1 || true
