# MVP Plan: Universal ai-use System

## Summary

Build a GitHub-first MVP that estimates what percentage of added PR lines originated from AI edits captured locally from Cursor, Claude Code, and Codex.

The MVP proves the core attribution loop first:

1. Local hooks/adapters capture AI edit evidence.
2. Evidence is stored as normalized chunk metadata plus line hashes only.
3. A GitHub Action parses PR diffs.
4. The matcher compares final added PR lines against captured AI line hashes.
5. The Action posts one sticky PR comment with attribution metrics.

## Key Changes

- Create a small CLI installer that configures local telemetry capture for Cursor hooks, Claude Code hooks/session events where available, and Codex local event/session capture where available.
- Define one normalized event format for all tools: `tool`, `repo_id`, `commit_base`, `file_path`, `event_time`, `chunk_id`, `line_hashes`, and optional metadata.
- Store hashes only by default. Normalize line text before hashing, do not persist raw generated code, and retain enough metadata to debug attribution at file/chunk level.
- Add a GitHub Action workflow that runs on pull requests, parses the diff, reads telemetry artifacts, computes attribution, and updates one sticky PR comment.
- Keep the first reporting surface GitHub-only. There is no hosted backend, auth system, or standalone dashboard in the MVP.

## Matching Behavior

- Attribute a final added PR line to AI when its normalized hash matches a captured AI line hash for the same repository and preferably the same file path.
- Count only final added lines in the PR diff.
- Do not mark an entire file as AI-authored just because AI touched it.
- Treat unmatched lines as unknown/human for MVP reporting.
- Include confidence buckets: `exact_file_match`, `cross_file_match`, and `unmatched`.

## Test Plan

- Unit test line normalization and hashing.
- Unit test PR diff parsing with added, removed, renamed, and modified files.
- Unit test matcher behavior for exact file matches, cross-file matches, duplicate lines, blank lines, and unmatched lines.
- Fixture-test each adapter using representative Cursor, Claude Code, and Codex event samples.
- End-to-end test with a sample repo using a synthetic PR diff and telemetry fixture.

## Assumptions

- MVP supports Cursor, Claude Code, and Codex from day one through separate adapters feeding one shared schema.
- Telemetry storage is hash-only by default.
- Engineer install path is a CLI installer, not manual templates or an npm package requirement.
- GitHub PR comment is the only MVP reporting surface.
- The future dashboard will be planned after the attribution engine and event schema are proven.
