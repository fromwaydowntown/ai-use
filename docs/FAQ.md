# FAQ

## Privacy

### Does any code leave my repo?
**No.** Every event stored — locally in `.ai-use/events.ndjson` and remotely in `refs/ai-attribution/*` — is a SHA-256 hash of one normalized line. No raw line content, no diffs, no file contents. The only "code-like" data stored is the file path the line came from, which is already public in your git history.

### Can someone reverse the hashes to recover code?
For long, distinctive lines (typical code): no — SHA-256 is one-way and there's no dictionary that contains arbitrary code snippets. For short lines (like `import json` or `API_KEY = "abc"`): theoretically yes, with a dictionary attack. We mitigate this two ways:
1. Lines shorter than 8 characters after whitespace-trim are **not hashed at all** (stored as a null sentinel)
2. Anyone trying to crack a 40-character line of business logic via dictionary attack is going to have a bad time

**If you're worried about specific secrets ending up in `events.ndjson`:** the same hooks that capture AI edits would capture any AI-written secret too. The real fix is "don't have AI write secrets," not "don't hash lines." But the hash isn't reversible in any practical sense for substantive code.

### Where is the data stored?
- **Locally:** `.ai-use/events.ndjson` (gitignored — never committed to the repo)
- **Remote:** `refs/ai-attribution/<sha256(your-email)[:16]>` on the same GitHub remote as the repo
- Nothing sent to any third-party server. Authentication uses your normal git push credentials.

### Who can see my attribution data?
Anyone with read access to the GitHub repo can `git fetch refs/ai-attribution/*` and see the per-developer event blobs. That's intentional — the PR analysis workflow needs to fetch all developers' data to compute org-wide stats. The data is hash-only, but if you treat your AI hash data as sensitive (e.g., performance-review-sensitive), it has the same trust boundary as the repo itself.

### Is anyone tracked individually?
Yes and no. Refs are keyed by `sha256(git user.email)[:16]`, which is pseudonymous. Anyone who knows the developer's email can recompute the hash and find their ref. So this is **pseudonymous, not anonymous.** It's the right level of identifiability for most teams: enough to debug "whose ref is broken?", not enough to feel like surveillance.

If you want stronger anonymity at the cost of debuggability, set everyone's `user.email` to the same value (this would also break attribution — don't do this in production).

## Accuracy

### How accurate is the AI percentage?
**Systematically under-counted.** The reported number is a lower bound on AI involvement, never an upper bound. If we report 40% AI, the real number is probably 50–70%.

Reasons for under-counting:
- Any character change to an AI-written line breaks the hash and re-classifies it as human
- AI exploration / scaffolding that doesn't end up in the final code isn't counted
- Lines under 8 chars never hash (kills false positives, but also misses real short AI lines)
- We disabled cross-file matching (AI line moved to a different file → unattributed)

Reasons for occasional over-counting (rare):
- Two developers independently writing the same line. With exact-file-path matching this is uncommon.

### Why did we disable cross-file matching?
The original implementation matched a PR line to AI if its hash appeared in *any* AI chunk, regardless of file. This produced catastrophic false-positives — one developer's AI-written `import json` would cause every `import json` in every PR across the org to be attributed to AI. Now we require an exact `(file_path, line_hash)` match. The cost: AI-helped refactors that move code between files are no longer cross-attributed. The benefit: numbers actually mean something.

### Why are blank lines reported as human?
Blank lines and very short lines (`}`, `pass`, `);`) are intentionally not hashed. They'd collide constantly across unrelated chunks and inflate the AI% by 10–30 points of noise. Lines under 8 normalized characters always count as human.

### Can I trust the trend even if the absolute number is conservative?
Yes — the systematic under-count is *consistent*, so week-over-week and month-over-month comparisons are meaningful. The absolute number is a lower bound; the *trend* is the real signal.

## Operation

### What if a developer's `git config user.email` is unset?
The pre-push hook refuses to upload events with a clear error message:
> `ai-use: git user.email is not configured. Set it with: git config --global user.email you@example.com`

The hook exits 0 (doesn't block the push), so the developer's `git push` still works — they just won't have their AI usage counted until they configure their email. This is intentional: we'd rather miss a developer's data than silently collapse multiple developers onto the same "unknown" ref.

### What happens on fork PRs?
Fork PRs run with a read-only `GITHUB_TOKEN` that can't post Check Runs. The workflow detects the 403, logs a warning, and exits 0 — the PR still merges normally, it just doesn't get an attribution Check Run. The analysis output is still in the workflow logs.

### What happens if the workflow fails?
PRs continue to merge. The attribution Check Run has `conclusion: neutral` — it never blocks a merge even when it succeeds. If the workflow fails for any reason (network, API rate limit, malformed data), the PR is unaffected.

### How much CI time does this cost?
Per PR: ~30–60 seconds (mostly Python install). Per push to main: similar. For a busy monorepo (100 PRs/day), that's ~50–100 minutes of CI/day. Negligible compared to a typical CI bill but worth knowing.

### Does it work on private repos?
Yes. The whole design assumes private repos — that's why everything is hash-only and uses native git auth instead of a cloud service.

### Does it work with GitHub Enterprise?
Yes, as long as the runners can reach `api.github.com` (or the GHE API endpoint) for posting Check Runs. The git ref push works regardless.

### Does it work with Copilot?
Not yet. Copilot doesn't expose a per-edit hook the way Cursor and Claude Code do. Adding it would require either Copilot Enterprise's audit log API or a different capture mechanism. If you'd like Copilot support, open an issue.

## Troubleshooting

### My PR shows 0% AI but I used Cursor / Claude Code the whole time
Run through the checks in order:
1. **Did your IDE actually invoke the hook?** Check that `.cursor/hooks.json` or `.claude/settings.json` exists and contains the `collect-ai-event.sh` command.
2. **Did the hook produce events?** Look at `.ai-use/events.ndjson` — should be non-empty after some AI edits.
3. **Did your pre-push fire?** Check `git config user.email` is set. If it's unset, the pre-push silently exits without uploading.
4. **Did the ref get pushed?** `git ls-remote origin 'refs/ai-attribution/*'` should show your hashed-email ref.
5. **Did the workflow fetch refs?** Look at the workflow logs for the "Fetch attribution refs" step.
6. **Did you edit the AI lines before commit?** Any character change breaks the hash. Common pattern: AI writes, you tweak indentation, hash doesn't match.

### Numbers seem wildly off from reality
The reported % is conservative by design. If your team reports 35% but feels like it should be 70%, that's normal — the gap is edited AI lines, refactors, and short-line filtering. Trust the *trend*, not the absolute number.

If the trend is also off (flat when usage is rising, or vice versa), suspect:
- A developer's hooks aren't firing (silent broken install)
- A developer's `user.email` is unset (their data isn't uploaded)
- Files added in PRs are mostly excluded from attribution (large generated files, lockfiles)

### Workflow fails with 403 on Check Run posting
Either (a) the PR is from a fork (expected — the workflow gracefully skips), or (b) the workflow's `permissions:` block is missing `checks: write`. Verify `.github/workflows/ai-use.yml` has:

```yaml
permissions:
  contents: read
  checks: write
```

### Dashboard shows "No attribution events recorded yet" even though developers have used AI
Likely no one's pre-push has fired yet. The dashboard reads from `refs/ai-attribution/*` on the remote. If no developer has pushed since installing, the refs are empty. Have one developer make a commit with AI edits and push.

### `docs/AI_USAGE.md` doesn't update
The dashboard workflow only commits if the file content changed. If your week's stats are identical to last week's, you'll see "No dashboard changes." in the workflow log and no commit. To force a refresh: `gh workflow run "AI Usage Dashboard"`.

## Uninstall

See the README's [Uninstall](../README.md#uninstall) section.

## Supply chain

### What does `curl … | bash` actually run?
[`install.sh`](../install.sh) — 20 lines, no obfuscation. It:
1. Checks you're inside a git repo
2. Verifies `python3` is on `PATH`
3. Creates an isolated venv at `~/.ai-use-venv` (won't touch system Python)
4. `pip install --force-reinstall git+https://github.com/fromwaydowntown/ai-use.git` (always the latest `main`)
5. Runs `ai-use install --commit` in the current repo

The install pulls the latest `main` on every run. If the upstream repo were compromised, the next CI run in any org using the bundled workflow would also pull the compromised code. The mitigation:
- This repo has branch protection on `main` (PRs only)
- Force-pushes to `main` are disabled
- Only the repo owner can merge

If you want to pin to a specific commit:
```bash
pip install "git+https://github.com/fromwaydowntown/ai-use.git@<commit-sha>"
ai-use install
```

### What if I want to fork it and host my own?
Encouraged. Replace `fromwaydowntown/ai-use` in `install.sh` and in `src/ai_use/data/*workflow.yml` with your own repo. That isolates you from any upstream supply-chain risk entirely.
