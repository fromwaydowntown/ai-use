# ai-use

**Website:** https://fromwaydowntown.github.io/ai-use/

You're spending on AI tooling. Are developers actually using it? Is it shipping?

Most teams can't answer that. Billing dashboards show token spend. They don't show how much of that output survives code review and lands in `main`.

**ai-use tracks the percentage of shipped lines that came from AI — per PR, per developer, over time.**

```
AI usage · `██████░░░░` 61% AI · 49/80 lines
```

No servers. No secrets. Hashes only — no code leaves your repo.

---

## Why it matters

AI tooling is a real budget line. Seat costs, token limits, enterprise plans — it adds up. But adoption is invisible. A developer can have Claude Code open all day and still write everything by hand. You'd never know.

ai-use gives you a trend:

```
Jan  ██░░░░░░░░  22%   ← rolled out Claude Code
Feb  ████░░░░░░  38%   ← raised token limits
Mar  ██████░░░░  61%   ← added to onboarding
Apr  ████████░░  79%   ← workflow settled
```

Flat or dropping? Something's broken in the workflow — wrong tool, wrong limits, not enough training. Rising? Your investment is landing.

That's the number you bring to a planning meeting.

---

## Setup

Run this from inside any git repo. No tokens or secrets needed.

```bash
curl -sSL https://raw.githubusercontent.com/fromwaydowntown/ai-use/main/install.sh | bash
```

The installer:
1. Creates an isolated Python venv at `~/.ai-use-venv` (won't touch your system Python)
2. Installs the `ai-use` CLI from this repo
3. Writes IDE hooks (Cursor, Claude Code), git hooks (pre-commit, pre-push), and two GitHub Actions workflows
4. Commits and pushes the changes

Every PR from then on gets a Check Run with the AI%. Every push to `main` refreshes `docs/AI_USAGE.md` with project-wide trends.

**Pre-flight:** every developer needs `git config user.email` set. Without it, the pre-push hook refuses to upload (this is intentional — it prevents collisions on a default "unknown" identity).

---

## Architecture

The tool is built around one principle: **never let raw code leave the repo.** Every event the system stores is a SHA-256 hash of one line. The rest is metadata (file path, tool, timestamp). If the GitHub repo and the developer's hard drive both go up in flames, no source code is recoverable from our data.

### Data flow

```
┌──────────────────────────────────────────────────────────────────────┐
│  Developer's machine                                                  │
│                                                                       │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────────────┐   │
│  │  Cursor /   │───▶│ collect-ai-  │───▶│ .ai-use/                │   │
│  │ Claude Code │    │  event.sh    │    │   events.ndjson         │   │
│  │             │    │ (IDE hook)   │    │   (line hashes only)    │   │
│  └─────────────┘    └──────────────┘    └─────────────────────────┘   │
│                                                       │               │
│  ┌─────────────┐    ┌──────────────┐                  │               │
│  │   Codex     │───▶│ pre-commit   │──────────────────┘               │
│  │ Desktop     │    │  git hook    │                                  │
│  └─────────────┘    └──────────────┘                                  │
│                                                       │               │
│                                                       ▼               │
│                                            ┌──────────────────┐       │
│                                            │   pre-push       │       │
│                                            │   git hook       │       │
│                                            └──────────────────┘       │
└──────────────────────────────────────────────────────┬────────────────┘
                                                       │ git push
                                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  GitHub remote                                                        │
│                                                                       │
│   refs/ai-use/<sha256(email)[:16]>                                    │
│      (one git blob per developer, holds their events.ndjson)          │
│                                                                       │
│   On PR opened / synchronize / closed:                                │
│     1. workflow fetches all refs/ai-use/*                             │
│     2. downloads PR diff                                              │
│     3. matches each diff line's hash against fetched events           │
│     4. posts a Check Run with the AI%                                 │
│                                                                       │
│   On push to main:                                                    │
│     dashboard workflow refreshes docs/AI_USAGE.md                     │
└──────────────────────────────────────────────────────────────────────┘
```

### Capture: IDE hooks

When you save a file edited with AI, the IDE invokes the local hook script (`.ai-use/hooks/collect-ai-event.sh`). The hook reads the IDE's tool-call payload from stdin, normalizes each line, hashes it with SHA-256, and appends an `AiCodeChunk` record to `.ai-use/events.ndjson`.

Each chunk records: `tool` (cursor/claude_code/codex), `file_path` (repo-relative), `line_hashes` (tuple of SHA-256 hex strings), `event_time`, `commit_base` (current HEAD), and tool-specific metadata. **No raw line content is ever written.**

Hooks are configured per-IDE:
- **Cursor** — `.cursor/hooks.json`, fires on `afterFileEdit` and related events.
- **Claude Code** — `.claude/settings.json`, fires on `PostToolUse` for `Edit|MultiEdit|Write`.
- **Codex Desktop** — has no per-repo hook; the pre-commit git hook runs `import-codex-session.sh` which reads the latest `~/.codex/sessions/*.jsonl`, filters to changes inside the current repo, and imports them.

### Lines that are *not* tracked

To prevent false-positive matches from trivial collisions, lines shorter than 8 characters (after normalization) are intentionally **never hashed** — they're stored as `NULL_HASH = ""` and the matcher treats them as always-unmatched (i.e., human-written). This kills the otherwise-pathological case where one AI user's blank lines would match every blank line in every PR to AI.

### Transport: per-developer git refs

On every `git push`, the pre-push hook (`.ai-use/hooks/upload-ref.sh`) stores `events.ndjson` as a git blob and force-pushes it to:

```
refs/ai-use/<sha256(your-email)[:16]>
```

Each developer has their own ref so two devs pushing simultaneously never conflict. Authentication piggybacks on your normal git push credentials — no tokens, no secrets. The hook refuses to push if `git config user.email` is unset.

### Analysis: per-PR Check Run

On `pull_request` events, `.github/workflows/ai-use.yml` runs:

1. `actions/checkout` with `fetch-depth: 0`
2. `git fetch origin '+refs/ai-use/*:refs/ai-use/*'` to pull every developer's chunks
3. `pip install` the ai-use CLI
4. `ai-use fetch-telemetry --github-native` concatenates all refs into `fetched-events.ndjson`
5. `gh pr diff` downloads the PR diff
6. `ai-use analyze-pr --post-check`:
   - Parses the unified diff into `AddedLine` records (`file_path` + `line_hash` + `text`)
   - Filters out installer-generated files (`.ai-use/`, the two workflow YAMLs, `.cursor/`, `.claude/`, `docs/AI_USAGE.md`)
   - Hashes each added line; looks for `(file_path, line_hash)` exact match in any chunk
   - Posts a Check Run with the result

Cross-file matching is **deliberately disabled** — too many false positives on common boilerplate (`import json`, `}`, etc.). Only exact file-path matches count as AI-written.

### Aggregation: project-wide dashboard

`.github/workflows/ai-use-dashboard.yml` runs on push to `main` (and daily at 06:00 UTC):

1. Same checkout + ref-fetch as the PR workflow
2. `ai-use render-dashboard --github-native --output docs/AI_USAGE.md`:
   - Aggregates AI lines per week per tool from the fetched chunks
   - Runs `git log --numstat` for the same window to get total added lines per week
   - Computes AI% = AI lines / total added lines per week (the real denominator, not just plotting absolute counts)
   - Emits markdown with native Mermaid charts (KPI cards, trend line, per-tool bars)
3. Commits the file if changed and pushes back to `main`

### Why this design

| Constraint | Choice |
|---|---|
| No code leaves the repo | SHA-256 hashes, never raw lines |
| No central server, no tokens | Per-developer git refs, native git auth |
| Works on private repos | All data stays inside the repo; no external SaaS |
| Resists trivial collisions | Drop short lines; require exact file-path match |
| Multi-developer safety | Per-user ref derived from `user.email` hash; collisions made loud, not silent |
| Fork PRs don't break workflow | Check Run posting gracefully degrades when the token lacks `checks:write` |

---

## What's measured (and what isn't)

**Counted as AI:** lines that survive review and are present in the merged PR's diff, at the *same file path*.

**Not counted:**
- AI-written lines edited by a human (any character change breaks the hash)
- AI exploration / scaffolding that didn't end up in the final code
- AI-written lines moved between files (cross-file matching is disabled)
- Lines shorter than 8 characters after whitespace trim (deliberately, to avoid collisions)

The number is **systematically conservative** — actual AI involvement is higher than the reported %. That's by design: we'd rather under-report than falsely flag a developer.

See the [FAQ](docs/FAQ.md) for more on accuracy, privacy, and troubleshooting.

---

## Dashboard

```bash
ai-use dashboard --repo .
# open http://127.0.0.1:8787
```

Local-only HTTP server. Same data as the auto-generated `docs/AI_USAGE.md`, with interactive charts.

---

## Uninstall

From a repo where you installed it:

```bash
git rm -r --ignore-unmatch \
  .ai-use \
  .github/workflows/ai-use.yml \
  .github/workflows/ai-use-dashboard.yml \
  .claude/settings.json .cursor/hooks.json \
  docs/AI_USAGE.md
rm -f .git/hooks/pre-commit .git/hooks/pre-push
git commit -m "chore: remove ai-use"
```

To also wipe historical events from the remote:

```bash
git push origin --delete $(git ls-remote origin 'refs/ai-use/*' | awk '{print $2}')
```

---

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
pytest
```

71 tests, runs in ~1.5s.

## Rollout

Planning to roll this out at your org? Read [docs/ROLLOUT.md](docs/ROLLOUT.md) — pilot plan, monitoring checklist, rollback procedure.
