#!/usr/bin/env bash
set -e

REPO="https://github.com/fromwaydowntown/ai-pr-attribution"
VENV="$HOME/.ai-pr-attribution-venv"

if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "Error: run this from inside a git repository." >&2
  exit 1
fi

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 not found. Install Python first: https://python.org" >&2
  exit 1
fi

python3 -m venv "$VENV" --quiet
"$VENV/bin/pip" install --quiet "git+$REPO.git"
"$VENV/bin/ai-pr-attribution" install --commit
