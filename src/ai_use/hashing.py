from __future__ import annotations

import hashlib

# Minimum length of a normalized line before we hash it.
# Lines shorter than this (blank lines, single punctuation like `}`, `);`,
# short keywords like `pass`, `return`) carry almost no signal and would
# collide across thousands of unrelated chunks — producing massive
# false-positives in cross-chunk attribution. We treat them as
# un-attributable (always reported as human-written).
MIN_HASHABLE_LENGTH = 8

NULL_HASH = ""  # sentinel: a line that wasn't hashed (too short / blank)


def normalize_line(line: str) -> str:
    """Normalize one source line before hashing.

    Normalizes line endings, strips a leading BOM (Windows files), and trims
    leading/trailing whitespace so that indentation changes (tabs vs spaces,
    re-indent) don't break attribution.
    """
    normalized = line.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.startswith("﻿"):
        normalized = normalized.lstrip("﻿")
    return normalized.strip()


def hash_line(line: str) -> str:
    """Hash a single line, or return NULL_HASH if the line is too short.

    Returns the empty string for blank or trivially short lines. The matcher
    treats NULL_HASH as never-matching, so those lines are always reported as
    unattributed (i.e., human-written), avoiding cross-chunk collisions on
    common boilerplate like blank lines, `}`, or `pass`.
    """
    normalized = normalize_line(line)
    if len(normalized) < MIN_HASHABLE_LENGTH:
        return NULL_HASH
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_lines(text: str) -> tuple[str, ...]:
    """Hash every line, including NULL_HASH for lines below the threshold.

    The full tuple is returned (including empties) so that callers can count
    total lines processed if needed. Filtering is done downstream where
    storage matters.
    """
    return tuple(hash_line(line) for line in text.splitlines())


def hashable_line_hashes(text: str) -> tuple[str, ...]:
    """Like hash_lines but drops NULL_HASH entries — for storage in chunks."""
    return tuple(h for h in hash_lines(text) if h)
