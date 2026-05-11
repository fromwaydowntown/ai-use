# AI PR Attribution

Know how much of your PR was written by AI — automatically, with no extra infrastructure.

Hooks capture AI edits locally as line hashes. On every push those hashes go to a git ref in your repo. When a PR is opened or merged, a GitHub Action compares the hashes against the diff and posts a one-line comment:

```
AI attribution · `███████░░░` 70% AI · 28/40 lines · Claude Code: 22L · Cursor: 6L
```

## Install

```bash
# one-time setup per repo — no secrets, uses your existing gh auth
ai-pr-attribution install --repo . --github-native
```

This sets up:
- Claude Code + Cursor hooks that capture edits as hash-only events
- A `pre-push` git hook that uploads events to `refs/ai-attribution/<you>` on every push
- No code content is stored anywhere — only normalized line hashes

Then commit the workflow:

```bash
cp .github/workflows/ai-pr-attribution.yml path/to/your/repo/.github/workflows/
```

That's it. Every PR gets an attribution comment. No collector server, no secrets to manage.

## How it works

1. **Local hooks** fire on every AI edit (Claude Code `PostToolUse`, Cursor hooks)
2. **`git push`** uploads a blob of line hashes to `refs/ai-attribution/<user-hash>` — one ref per developer, no conflicts
3. **GitHub Actions** fetches all `refs/ai-attribution/*`, concatenates them, diffs the PR, matches hashes, posts the comment
4. **At merge**, the workflow re-runs on the final diff and marks the comment as the confirmed score

## Local dashboard

```bash
ai-pr-attribution dashboard --repo .
# open http://127.0.0.1:8787
```

Shows AI lines captured, tool breakdown, daily activity, and retention rate into the current branch.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
pytest
```
