from __future__ import annotations

import json

from ai_pr_attribution.schema import AttributionSummary, LineAttribution

COMMENT_MARKER = "<!-- ai-pr-attribution:mvp -->"


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


def render_markdown(summary: AttributionSummary, attributions: list[LineAttribution], final: bool = False) -> str:
    rows = [
        ("Total added lines", str(summary.total_added_lines)),
        ("AI-attributed lines", str(summary.attributed_lines)),
        ("AI attribution", f"{summary.attribution_percent:.2f}%"),
        ("Exact file matches", str(summary.exact_file_match)),
        ("Cross-file matches", str(summary.cross_file_match)),
        ("Unknown / human lines", str(summary.unmatched)),
    ]
    table = "\n".join(f"| {name} | {value} |" for name, value in rows)
    tool_rows = "\n".join(f"| {tool} | {count} |" for tool, count in summary.by_tool.items()) or "| none | 0 |"
    files = _file_breakdown(attributions)
    file_rows = "\n".join(
        f"| {file_path} | {values['total']} | {values['attributed']} | {values['percent']:.2f}% |"
        for file_path, values in files.items()
    ) or "| none | 0 | 0 | 0.00% |"

    heading = "## AI PR Attribution — Final Score ✓" if final else "## AI PR Attribution"
    footer = (
        "_Final score recorded at merge time._"
        if final
        else "_Lines are attributed when normalized final PR additions match captured AI edit hashes._"
    )

    return f"""{COMMENT_MARKER}
{heading}

| Metric | Value |
| --- | ---: |
{table}

| Tool | Attributed lines |
| --- | ---: |
{tool_rows}

| File | Added lines | AI-attributed | AI % |
| --- | ---: | ---: | ---: |
{file_rows}

{footer}
"""


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
