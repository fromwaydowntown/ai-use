# Rollout runbook

How to deploy AI PR Attribution to a real engineering org without it blowing up in your face.

## Pre-rollout: 1 week out

### Decide what success looks like

Write this down before you ship anything. If you can't fill these in, **don't roll out yet** — you'll lose interest in the dashboard within a month.

- The decision this data will inform: ______________________
- The audience for the dashboard: ______________________
- The success criterion at 90 days: ______________________
- The "kill it" criterion at 90 days: ______________________

### Pre-flight checklist

- [ ] Every developer's `git config user.email` is set. The hook refuses to upload otherwise.
- [ ] Your team is on at least one supported tool: Cursor, Claude Code, or Codex Desktop. (Copilot is **not** supported.)
- [ ] You have admin access to the repo (to merge the auto-generated workflow commits).
- [ ] Branch protection on `main` allows the `github-actions[bot]` to push (the dashboard workflow commits `docs/AI_USAGE.md` directly). If not, set up a bypass or move the dashboard to a separate branch.
- [ ] You've previewed the FAQ and shared the privacy framing with the team **before** installing anywhere.

### Privacy framing for the team

Lead with this — don't let anyone find out about the tool by noticing a new git commit:

> We're rolling out a tool that measures team-wide AI tool adoption. It only stores SHA-256 hashes of individual code lines — never raw code. We're tracking team-level trends, not individual performance. Refs are pseudonymous (hashed email). The goal is to know whether the $X we spend on AI tools is producing shipped code; the goal is **not** to single anyone out. Here's the FAQ: [link].

If anyone has concerns about being identified, hear them out. Pseudonymous != anonymous. If concerns are blocking, you can configure all team members to use the same `user.email` for attribution (this breaks per-developer breakdown but preserves org-wide stats).

## Day 1 (Monday): Pilot one team

**Do not roll out org-wide on day 1.** Pick one team:

- 4–8 developers
- Active AI users (so the dashboard actually shows signal, not a flat line)
- A tolerant team lead who'll surface issues quickly

### Install steps

For each developer on the pilot team:

```bash
cd <repo>
curl -sSL https://raw.githubusercontent.com/fromwaydowntown/ai-use/main/install.sh | bash
```

The installer auto-commits and pushes. Watch the team Slack for "what's this commit?" questions — pre-empt them with a note.

### Day-1 verification

After everyone installs:

```bash
# Each developer:
ls .ai-use/hooks/        # should list 3 scripts
cat .cursor/hooks.json              # should reference collect-ai-event.sh
cat .claude/settings.json           # same
ls .git/hooks/pre-commit .git/hooks/pre-push   # both should exist

# Team lead:
git fetch origin '+refs/ai-attribution/*:refs/ai-attribution/*'
git for-each-ref refs/ai-attribution/   # should grow as devs push
```

After the first 24 hours of work, each developer should have an entry. If anyone's missing:
1. Did they push at all? Check git log for their commits.
2. Is `user.email` set? `git config user.email`
3. Did their pre-push fire? Look in `~/.git-hook-debug` if you've enabled hook logging.

## Days 2–7: Watch and calibrate

### Do not trust the first week's numbers

Hooks take a few days to settle in. People learn that AI edits captured-then-tweaked don't count. The W-1 number will look low. **Set this expectation up front.**

### What to monitor

| Signal | Where to look | What to do |
|---|---|---|
| Workflow failures | `gh run list --workflow=ai-use.yml` | Investigate any failing run. Common cause: missing `checks: write` permission. |
| Coverage gaps | `git for-each-ref refs/ai-attribution/` count vs team size | Chase missing developers. |
| Dashboard freshness | `docs/AI_USAGE.md` last-modified timestamp | Should refresh on every push to main + daily at 06:00 UTC. |
| %AI plausibility | Compare to each dev's gut-feel | "Does your reported % feel roughly right?" Calibrate trust before scaling. |
| CI cost | GitHub Actions usage page | Should be a few minutes per PR, max. |

### Common day-1-week issues

**"My number is way lower than I expected."** Expected. The tool is systematically conservative — see the FAQ. Trust the trend, not the absolute.

**"The workflow failed with 403."** Fork PR — the workflow gracefully skips Check Run posting. If it's not a fork, check the `permissions:` block in the workflow YAML.

**"My commits show up but my AI usage doesn't."** Either the hook didn't fire (broken IDE config), or `user.email` is unset. Verify both.

**"The check appeared as 0% but I clearly used AI."** Probably edited the AI lines after writing them. Hash mismatch = unmatched.

## Days 8–30: Expand

After one week of stable data from the pilot team:

1. **One more team per week.** Don't go org-wide all at once.
2. Add the install command to your **onboarding docs** so new joiners install it day 1.
3. Add `ai-use install` to any `make setup` / `bin/setup` script you have.
4. Audit ref coverage monthly: `git for-each-ref refs/ai-attribution/ | wc -l` should be close to your active dev count.

## 90-day checkpoint

At 90 days post-rollout, check against the criteria you wrote at the start:

- Hit success criterion? → Continue. The tool earned its keep.
- Hit kill criterion? → Uninstall. Don't sunk-cost it.
- In between? → Pick one concrete next step (e.g., add cost-per-line, integrate with PR cycle time) and reassess in 30 more days.

## Failure modes and mitigations

### Worst case 1: Numbers look wildly wrong on rollout day
Mitigation:
1. Have the [Uninstall](../README.md#uninstall) command in a note before you start.
2. If pilot data is obviously bad, uninstall from the pilot repo, debug locally, redeploy.
3. The damage is contained to one team — that's why you piloted.

### Worst case 2: Dev complains about surveillance
Mitigation:
1. You already framed it as team-level, not individual. Re-share the FAQ privacy section.
2. If they still object: offer to wipe their ref. `git push origin --delete refs/ai-attribution/<their-hash>`. They can still use the tools without their data being captured (`mv .cursor/hooks.json .cursor/hooks.json.disabled`).
3. If multiple people object: pause the rollout, address the concern, restart.

### Worst case 3: CI explodes on a busy PR day
Mitigation:
1. The workflow has `conclusion: neutral` — it never blocks merges even when it succeeds.
2. If it's *failing*, it shows as a red check but devs can still merge (assuming you didn't make it a required check — don't make it a required check).
3. To temporarily disable: `gh workflow disable "AI PR Attribution"`.

### Worst case 4: A secret leaked into events.ndjson and got pushed
Mitigation:
1. Events are hashed, so the secret isn't directly recoverable. But hashes of short secrets *are* dictionary-attackable.
2. Wipe the affected developer's ref: `git push origin --delete refs/ai-attribution/<their-hash>`.
3. Wipe their local events: `rm .ai-use/events.ndjson`.
4. **Also**: rotate the actual secret — assume hash-of-secret is as good as leaked secret for any short value.

### Worst case 5: Workflow keeps committing to main and you can't merge anything
Mitigation:
1. Disable the dashboard workflow: `gh workflow disable "AI Usage Dashboard"`.
2. The attribution workflow doesn't commit, only the dashboard one does — main becomes mergeable again immediately.
3. Investigate root cause (likely the dashboard workflow is racing with another commit). The workflow has `concurrency: { group: dashboard, cancel-in-progress: false }` to prevent this, but it's worth verifying.

## Rollback

To fully uninstall from a repo:

```bash
git rm -r --ignore-unmatch \
  .ai-use \
  .github/workflows/ai-use.yml \
  .github/workflows/ai-use-dashboard.yml \
  .claude/settings.json .cursor/hooks.json \
  docs/AI_USAGE.md
rm -f .git/hooks/pre-commit .git/hooks/pre-push
git commit -m "chore: remove AI PR attribution"
git push
```

To wipe the historical data from the remote:

```bash
git push origin --delete $(git ls-remote origin 'refs/ai-attribution/*' | awk '{print $2}')
```

Each developer should also clean up locally:

```bash
rm -rf .ai-use
rm -rf ~/.ai-use-venv  # only if uninstalling tool entirely
```

## Things that will eventually go wrong

Plan for these — none are blockers but they'll happen:

- A new IDE version changes its hook payload format → some events stop being captured
- Someone's `user.email` changes (job change, marriage, etc.) → their old ref orphans, new ref starts fresh
- A repo rename → workflow logs the new name, refs may break briefly
- A force-push to main → dashboard workflow loses one update cycle, recovers on next push
- A developer leaves the company → their ref stays in the remote until you wipe it manually

## Monitoring after rollout

Weekly, for the first month:

```bash
# Active refs (should match your active dev count)
git ls-remote origin 'refs/ai-attribution/*' | wc -l

# Last 10 workflow runs (should be mostly green)
gh run list --workflow=ai-use.yml --limit 10

# Dashboard freshness
git log -1 --format=%ai docs/AI_USAGE.md
```

If any of these go sideways for more than a few days, investigate.
