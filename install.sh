#!/usr/bin/env bash
set -e

REPO="https://github.com/fromwaydowntown/ai-use"
VENV="$HOME/.ai-use-venv"

if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "Error: run this from inside a git repository." >&2
  exit 1
fi

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 not found. Install Python first: https://python.org" >&2
  exit 1
fi

python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --force-reinstall "git+$REPO.git"
"$VENV/bin/ai-use" install --commit
