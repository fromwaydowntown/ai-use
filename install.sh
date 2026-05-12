#!/usr/bin/env bash
set -e

REPO="https://github.com/fromwaydowntown/ai-pr-attribution"

if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "Error: run this from inside a git repository." >&2
  exit 1
fi

if command -v pip3 &>/dev/null; then
  pip3 install --quiet "git+$REPO.git"
elif command -v pip &>/dev/null; then
  pip install --quiet "git+$REPO.git"
else
  echo "Error: pip not found. Install Python first: https://python.org" >&2
  exit 1
fi

ai-pr-attribution install --commit
