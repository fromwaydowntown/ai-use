# AI PR Attribution

Your team is spending on Claude Code. And Cursor. Maybe Codex too. Limits went up, plans changed, tools rotated — but nobody knows how much of that AI output actually ships.

**AI PR Attribution answers the question EMs and Staff engineers keep asking:**

> "We're paying for all these AI tools. How much of what they generate actually makes it into production?"

Every PR gets a score:

```
AI attribution · `███████░░░` 70% AI · 28/40 lines · Claude Code: 22L · Cursor: 6L
```

No servers. No secrets. No code leaves your repo.

---

## The problem

You switched from Copilot to Cursor. Then added Claude Code. Now Codex is in the mix. Token budgets are real, seat costs add up, and leadership wants to know if AI is actually accelerating the team — or just generating noise that gets rewritten anyway.

You can see token usage in billing dashboards. You cannot see how much of that usage survives code review and lands in `main`.

That gap is what this tool closes.

---

## How it works

```
  Developer writes code with Claude Code / Cursor / Codex
            │
            ▼
  Local hook fires on every AI edit
  (no code stored — only a hash of each line)
            │
            ▼
  git push  →  hashes uploaded to refs/ai-attribution/<you>
  (one ref per developer, no conflicts, uses existing git auth)
            │
            ▼
  PR opened or merged
            │
            ▼
  GitHub Action fetches all refs/ai-attribution/*
  diffs the PR, matches hashes, posts comment
            │
            ▼
  ✓ Final · ████████░░ 82% AI · 41/50 lines · Claude Code: 35L · Cursor: 6L
```

Two scores per PR:
- **On open** — snapshot of AI contribution at review time
- **On merge** — confirmed score against what actually shipped (lines reviewers rewrote are excluded)

---

## Setup

One command per repo. Uses your existing `gh` auth — no tokens, no secrets to manage.

```bash
pip install ai-pr-attribution
ai-pr-attribution install --repo . --github-native
```

Then add the workflow to your repo:

```bash
cp .github/workflows/ai-pr-attribution.yml your-repo/.github/workflows/
git add .github/workflows/ai-pr-attribution.yml
git commit -m "add AI attribution workflow"
git push
```

That's it. Every PR from here on gets an attribution comment automatically.

### What gets installed

| Component | What it does |
|---|---|
| Claude Code hook | Captures edits on `PostToolUse` / `Stop` |
| Cursor hook | Captures edits on file save and session end |
| `pre-push` git hook | Uploads line hashes to `refs/ai-attribution/<you>` |
| GitHub Action | Diffs PR, matches hashes, posts comment |

Nothing leaves your repo except anonymous line hashes. No raw code, no prompts, no context.

---

## Local dashboard

```bash
ai-pr-attribution dashboard --repo .
# open http://127.0.0.1:8787
```

Shows AI lines captured, tool breakdown by day, and retention rate — how much of what each tool generates actually stays in the branch.

---

## For EMs: what to do with the data

- **Low retention rate** (AI writes it, humans rewrite it) — the tool may be generating plausible-looking but wrong code. Worth a retro.
- **High token spend, low attribution** — AI is being used for exploration/research, not shipping. Not necessarily bad, but worth knowing.
- **Tool A outretains Tool B** — one tool's output is surviving review better. Useful signal when renewing seats or adjusting limits.
- **Attribution drops after a tool change** — the new tool may need a different workflow to be effective for your codebase.

---

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
pytest
```
