from __future__ import annotations

from collections import Counter, defaultdict

from ai_pr_attribution.schema import AddedLine, AiCodeChunk, AttributionSummary, LineAttribution


def attribute_lines(added_lines: list[AddedLine], chunks: list[AiCodeChunk]) -> list[LineAttribution]:
    by_file_hash: dict[tuple[str, str], AiCodeChunk] = {}
    by_hash: dict[str, AiCodeChunk] = {}

    for chunk in chunks:
        for line_hash in chunk.line_hashes:
            by_file_hash.setdefault((chunk.file_path, line_hash), chunk)
            by_hash.setdefault(line_hash, chunk)

    results: list[LineAttribution] = []
    for line in added_lines:
        exact = by_file_hash.get((line.file_path, line.line_hash))
        if exact:
            results.append(LineAttribution(line=line, confidence="exact_file_match", chunk_id=exact.chunk_id, tool=exact.tool))
            continue
        cross = by_hash.get(line.line_hash)
        if cross:
            results.append(LineAttribution(line=line, confidence="cross_file_match", chunk_id=cross.chunk_id, tool=cross.tool))
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
