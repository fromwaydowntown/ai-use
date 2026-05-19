from __future__ import annotations

import json

from ai_use.schema import AttributionSummary, LineAttribution

COMMENT_MARKER = "<!-- ai-use:mvp -->"


def summary_to_json(summary: AttributionSummary) -> str:
    return json.dumps(
        {
            "total_added_lines": summary.total_added_lines,
            "attributed_lines": summary.attributed_lines,
            "attribution_percent": summary.attribution_percent,
            "exact_file_match": summary.exact_file_match,
            "cross_file_match": summary.cross_file_match,
            "unmatched": summary.unmatched,
            "by_tool": summary.by_tool,
        },
        indent=2,
        sort_keys=True,
    )


TOOL_LABELS = {"claude_code": "Claude Code", "cursor": "Cursor", "codex": "Codex"}


def render_markdown(summary: AttributionSummary, attributions: list[LineAttribution], final: bool = False) -> str:
    pct = summary.attribution_percent
    bar = _mini_bar(pct)
    status = "✓ Final" if final else "·"

    tools = " · ".join(
        f"{TOOL_LABELS.get(tool, tool)}: {count}L"
        for tool, count in summary.by_tool.items()
        if count > 0
    ) or "no matches"

    return f"""{COMMENT_MARKER}
**AI attribution** {status} {bar} **{pct:.0f}%** AI &nbsp;·&nbsp; {summary.attributed_lines}/{summary.total_added_lines} lines &nbsp;·&nbsp; {tools}
"""


def render_check_run(summary: AttributionSummary, attributions: list[LineAttribution], final: bool = False) -> tuple[str, str]:
    """Return (title, summary_markdown) for a GitHub Check Run.

    The title is one short line (shown collapsed). The summary is full markdown
    with per-tool breakdown, per-file breakdown, and a confidence breakdown.
    """
    pct = summary.attribution_percent
    label = "Final" if final else "Preview"

    tool_summary = ", ".join(
        f"{TOOL_LABELS.get(tool, tool)} {count}L"
        for tool, count in summary.by_tool.items()
        if count > 0
    ) or "no AI matches"

    title = f"{label}: {pct:.0f}% AI ({summary.attributed_lines}/{summary.total_added_lines} lines) · {tool_summary}"

    bar = _mini_bar(pct)
    tool_rows = "\n".join(
        f"| {TOOL_LABELS.get(tool, tool)} | {count} |"
        for tool, count in sorted(summary.by_tool.items(), key=lambda kv: -kv[1])
        if count > 0
    ) or "| _none_ | 0 |"

    files = _file_breakdown(attributions)
    file_rows = "\n".join(
        f"| `{path}` | {int(v['attributed'])}/{int(v['total'])} | {v['percent']:.0f}% |"
        for path, v in files.items()
    ) or "| _none_ | 0/0 | 0% |"

    return title, f"""## {bar} **{pct:.0f}%** AI

**{summary.attributed_lines}** of **{summary.total_added_lines}** added lines attributed to AI.

### By tool
| Tool | Lines |
|---|---|
{tool_rows}

### By file
| File | AI / Total | % |
|---|---|---|
{file_rows}

### Confidence
- Exact file match: **{summary.exact_file_match}**
- Cross-file match: **{summary.cross_file_match}**
- Unmatched (human-written): **{summary.unmatched}**

<sub>{COMMENT_MARKER}</sub>
"""


def _mini_bar(pct: float) -> str:
    filled = round(pct / 10)
    return "`" + "█" * filled + "░" * (10 - filled) + "`"


def _file_breakdown(attributions: list[LineAttribution]) -> dict[str, dict[str, float]]:
    files: dict[str, dict[str, float]] = {}
    for item in attributions:
        bucket = files.setdefault(item.line.file_path, {"total": 0, "attributed": 0, "percent": 0.0})
        bucket["total"] += 1
        if item.confidence != "unmatched":
            bucket["attributed"] += 1
    for values in files.values():
        values["percent"] = 0.0 if values["total"] == 0 else round((values["attributed"] / values["total"]) * 100, 2)
    return dict(sorted(files.items()))
