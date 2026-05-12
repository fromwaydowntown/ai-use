from __future__ import annotations

import re

from ai_pr_attribution.hashing import hash_line
from ai_pr_attribution.schema import AddedLine

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

# Paths added by the installer itself — exclude from attribution analysis
_INSTALLER_PATHS = (
    ".ai-pr-attribution/",
    ".github/workflows/ai-pr-attribution.yml",
    ".claude/settings.json",
    ".cursor/hooks.json",
)


def parse_unified_diff(diff_text: str) -> list[AddedLine]:
    added: list[AddedLine] = []
    current_file: str | None = None
    new_lineno: int | None = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            current_file = None
            new_lineno = None
            continue
        if raw_line.startswith("+++ "):
            path = _clean_diff_path(raw_line[4:].strip())
            current_file = None if any(path.startswith(p) for p in _INSTALLER_PATHS) else path
            continue
        hunk = HUNK_RE.match(raw_line)
        if hunk:
            new_lineno = int(hunk.group(1))
            continue
        if current_file is None or new_lineno is None:
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            text = raw_line[1:]
            added.append(
                AddedLine(
                    file_path=current_file,
                    new_lineno=new_lineno,
                    text=text,
                    line_hash=hash_line(text),
                )
            )
            new_lineno += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            continue
        elif raw_line.startswith("\\ No newline at end of file"):
            continue
        else:
            new_lineno += 1

    return added


def _clean_diff_path(path: str) -> str:
    if path == "/dev/null":
        return path
    if path.startswith("b/") or path.startswith("a/"):
        return path[2:]
    return path
