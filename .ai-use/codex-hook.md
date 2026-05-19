# Codex Hook Adapter

Codex Desktop does not currently expose the same repo hook file shape as Cursor
or Claude Code. The installer adds a Git `pre-commit` hook that imports local
Codex session patch events before each commit.

Manual collection is also available:

```bash
AI_USE_TOOL=codex '/path/to/your/repo/.ai-use/hooks/collect-ai-event.sh'
```

The collector stores hash-only evidence in `.ai-use/events.ndjson`.
