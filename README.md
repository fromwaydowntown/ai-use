# AI PR Attribution

You're spending on AI tooling. Are developers actually using it? Is it shipping?

Most teams can't answer that. Billing dashboards show token spend. They don't show how much of that output survives code review and lands in `main`.

**AI PR Attribution tracks the percentage of shipped lines that came from AI — per PR, per developer, over time.**

```
AI attribution · `██████░░░░` 61% AI · 49/80 lines
```

No servers. No secrets. Hashes only — no code leaves your repo.

---

## Why it matters

AI tooling is a real budget line. Seat costs, token limits, enterprise plans — it adds up. But adoption is invisible. A developer can have Claude Code open all day and still write everything by hand. You'd never know.

Attribution gives you a trend:

```
Jan  ██░░░░░░░░  22%   ← rolled out Claude Code
Feb  ████░░░░░░  38%   ← raised token limits  
Mar  ██████░░░░  61%   ← added to onboarding
Apr  ████████░░  79%   ← workflow settled
```

Flat or dropping? Something's broken in the workflow — wrong tool, wrong limits, not enough training. Rising? Your investment is landing.

That's the number you bring to a planning meeting.

---

## How it works

```
  AI writes code  →  local hook captures line hashes (no raw code)
        │
        ▼
  git push  →  hashes uploaded to refs/ai-attribution/<you>
  (one ref per developer, no conflicts, uses existing git auth)
        │
        ▼
  PR opened  →  GitHub Action diffs PR, matches hashes, posts comment
        │
        ▼
  PR merged  →  ✓ Final score against what actually shipped
               (lines rewritten in review don't count)
```

Two scores per PR:
- **On open** — how much AI went into this at review time
- **On merge** — confirmed: how much AI actually shipped

---

## Setup

One command per repo. Uses your existing git credentials — no tokens or secrets needed.

```bash
pip install ai-pr-attribution && ai-pr-attribution install --commit
```

That's it. Every PR gets a comment. Every merge updates the score.

---

## Dashboard

```bash
ai-pr-attribution dashboard --repo .
# open http://127.0.0.1:8787
```

Attribution trend over time, per developer, per branch. The number to track when you're trying to move it.

---

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
pytest
```
