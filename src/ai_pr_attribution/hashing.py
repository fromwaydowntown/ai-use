from __future__ import annotations

import hashlib


def normalize_line(line: str) -> str:
    """Normalize one source line before hashing.

    The MVP preserves internal whitespace but ignores line endings and leading or
    trailing whitespace. Empty normalized lines are intentionally hashable so
    blank-line attribution can be tested and reported.
    """
    return line.replace("\r\n", "\n").replace("\r", "\n").strip()


def hash_line(line: str) -> str:
    normalized = normalize_line(line)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_lines(text: str) -> tuple[str, ...]:
    return tuple(hash_line(line) for line in text.splitlines())
