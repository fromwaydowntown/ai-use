# AI PR Attribution MVP

GitHub-first attribution for AI-generated code from Cursor, Claude Code, and Codex.

The MVP captures local AI edit evidence as normalized line hashes, compares those hashes to final added lines in a pull request diff, and posts a sticky GitHub PR comment with attribution metrics.

## Install for Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"
```

## One-Command Repo Install

From a repository where engineers write code:

```bash
ai-pr-attribution install --repo .
```

This installs local collection once:

- Cursor hook config in `.cursor/hooks.json`.
- Claude Code hook config in `.claude/settings.json`.
- A Git `pre-commit` hook that imports Codex Desktop session edits automatically.
- Hash-only local storage in `.ai-pr-attribution/events.ndjson`.

After this, engineers keep using Cursor, Claude Code, Codex, and Git normally.

For PR metrics, point the repo at a collector once:

```bash
ai-pr-attribution install --repo . --collector-url https://collector.example
```

Then `git push` uploads hash-only telemetry outside the PR diff. No telemetry file
is committed and no extra Git refs are created.

For local collector testing:

```bash
ai-pr-attribution serve-collector --host 127.0.0.1 --port 8765
ai-pr-attribution install --repo . --collector-url http://127.0.0.1:8765
```

## Capture Hook Events

Adapters call the collector with JSON on stdin:

```bash
echo '{"tool":"cursor","file_path":"app.py","text":"print(\"hello\")"}' \
  | ai-pr-attribution collect-hook --tool cursor --repo .
```

The collector stores hash-only NDJSON in `.ai-pr-attribution/events.ndjson`.

## Import Codex App Session Events

Codex Desktop records local session JSONL files. The one-command installer imports
Codex patch events automatically before commits. To import manually:

```bash
ai-pr-attribution import-codex-session --repo .
```

This imports added lines from local Codex patch events as hash-only chunks.

## Local Dashboard

Run a local dashboard for current repo usage:

```bash
ai-pr-attribution dashboard --repo .
```

Open `http://127.0.0.1:8787` to see AI edit events, AI lines captured, tool breakdown,
top files, and recent events. The page reads local hash-only telemetry and
refreshes automatically.

## Analyze a PR Diff

```bash
ai-pr-attribution analyze-pr \
  --repo . \
  --diff-file ./pr.diff \
  --events-file ./.ai-pr-attribution/events.ndjson
```

## GitHub Action

Copy `.github/workflows/ai-pr-attribution.yml` into a repository and configure
these secrets:

- `AI_ATTRIBUTION_COLLECTOR_URL`
- `AI_ATTRIBUTION_COLLECTOR_TOKEN` if the collector requires one.

On pull requests, the Action fetches the PR diff, downloads hash-only telemetry
for the PR head SHA from the collector, runs the matcher, and updates one sticky
PR comment.
