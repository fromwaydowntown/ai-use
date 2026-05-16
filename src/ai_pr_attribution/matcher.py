from __future__ import annotations

from collections import Counter, defaultdict

from ai_pr_attribution.hashing import NULL_HASH
from ai_pr_attribution.schema import AddedLine, AiCodeChunk, AttributionSummary, LineAttribution


def attribute_lines(added_lines: list[AddedLine], chunks: list[AiCodeChunk]) -> list[LineAttribution]:
    """Attribute each added line to an AI chunk, or mark it unmatched.

    Attribution is by exact (file_path, line_hash) match only. Cross-file
    matching was removed because it produced too many false-positives on
    common boilerplate — e.g., one AI user's `import json` would cause every
    PR's `import json` line in any file to be attributed to them.

    Lines whose hash is NULL_HASH (too short to hash reliably — blank lines,
    single punctuation, short keywords) are always reported as unattributed.
    """
    by_file_hash: dict[tuple[str, str], AiCodeChunk] = {}

    for chunk in chunks:
        for line_hash in chunk.line_hashes:
            if line_hash == NULL_HASH:
                continue
            by_file_hash.setdefault((chunk.file_path, line_hash), chunk)

    results: list[LineAttribution] = []
    for line in added_lines:
        if line.line_hash == NULL_HASH:
            results.append(LineAttribution(line=line, confidence="unmatched"))
            continue
        exact = by_file_hash.get((line.file_path, line.line_hash))
        if exact:
            results.append(LineAttribution(line=line, confidence="exact_file_match", chunk_id=exact.chunk_id, tool=exact.tool))
            continue
        results.append(LineAttribution(line=line, confidence="unmatched"))
    return results


def summarize(attributions: list[LineAttribution]) -> AttributionSummary:
    confidence = Counter(item.confidence for item in attributions)
    by_tool: dict[str, int] = defaultdict(int)
    for item in attributions:
        if item.tool:
            by_tool[item.tool] += 1
    return AttributionSummary(
        total_added_lines=len(attributions),
        exact_file_match=confidence["exact_file_match"],
        cross_file_match=confidence["cross_file_match"],
        unmatched=confidence["unmatched"],
        by_tool=dict(sorted(by_tool.items())),
    )
