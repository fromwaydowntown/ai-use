from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ai_use.diff_parser import parse_unified_diff
from ai_use.events import DEFAULT_EVENTS_PATH, read_chunks
from ai_use.git_utils import run_git
from ai_use.hashing import hash_line
from ai_use.matcher import attribute_lines, summarize
from ai_use.schema import AiCodeChunk


def build_summary(events_file: Path, repo: Path | None = None) -> dict:
    chunks = read_chunks(events_file)
    by_tool = Counter(chunk.tool for chunk in chunks)
    by_file: Counter[str] = Counter()
    lines_by_tool: Counter[str] = Counter()
    by_day: Counter[str] = Counter()
    for chunk in chunks:
        line_count = len(chunk.line_hashes)
        by_file[chunk.file_path] += line_count
        lines_by_tool[chunk.tool] += line_count
        day = _day(chunk.event_time)
        if day:
            by_day[day] += line_count

    kpis = _build_kpis(chunks, repo)
    retention = _retention_breakdowns(chunks, repo)
    return {
        "events_file": str(events_file),
        "total_chunks": len(chunks),
        "total_hashed_lines": sum(len(chunk.line_hashes) for chunk in chunks),
        "kpis": kpis,
        "readiness": _readiness(events_file, repo, chunks),
        "retention_by_tool": retention["by_tool"],
        "retention_by_file": retention["by_file"],
        "by_tool": dict(sorted(by_tool.items())),
        "lines_by_tool": dict(sorted(lines_by_tool.items())),
        "top_files": [{"file_path": path, "hashed_lines": count} for path, count in by_file.most_common(12)],
        "lines_by_day": [{"day": day, "hashed_lines": count} for day, count in sorted(by_day.items())[-14:]],
        "recent_chunks": [_chunk_row(chunk) for chunk in chunks[-25:]][::-1],
    }


def serve_dashboard(repo: Path, host: str, port: int, events_file: Path | None = None) -> None:
    repo = repo.resolve()
    resolved_events = events_file or repo / DEFAULT_EVENTS_PATH

    class Handler(DashboardHandler):
        dashboard_repo = repo
        dashboard_events_file = resolved_events

    ThreadingHTTPServer((host, port), Handler).serve_forever()


class DashboardHandler(BaseHTTPRequestHandler):
    dashboard_repo: Path
    dashboard_events_file: Path

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(render_dashboard_html(self.dashboard_repo))
            return
        if parsed.path == "/api/summary":
            self._send_json(build_summary(self.dashboard_events_file, self.dashboard_repo))
            return
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, format: str, *args) -> None:
        return

    def _send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def render_dashboard_html(repo: Path) -> str:
    repo_label = escape(str(repo))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Attribution Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f6f8;
      --surface: #ffffff;
      --surface-2: #f9fafb;
      --ink: #111827;
      --muted: #667085;
      --line: #d9e0ea;
      --line-soft: #edf1f5;
      --green: #147a5c;
      --blue: #2f68d8;
      --amber: #b56a09;
      --red: #b42318;
      --shadow: 0 1px 2px rgba(16, 24, 40, .06), 0 10px 24px rgba(16, 24, 40, .05);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 14px/1.45 Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    .shell {{ min-height: 100vh; }}
    .topbar {{
      height: 58px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 0 28px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, .94);
      position: sticky;
      top: 0;
      z-index: 10;
    }}
    .brand {{ display: flex; align-items: center; gap: 11px; min-width: 0; }}
    .mark {{
      width: 30px;
      height: 30px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      color: #fff;
      background: linear-gradient(135deg, var(--green), var(--blue));
      font-weight: 800;
      font-size: 13px;
    }}
    .brand-title {{ font-size: 15px; font-weight: 700; white-space: nowrap; }}
    .brand-subtitle {{ color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 48vw; }}
    .top-actions {{ display: flex; align-items: center; gap: 10px; }}
    .status-pill {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      height: 30px;
      padding: 0 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--surface-2);
      color: #344054;
      font-size: 12px;
      white-space: nowrap;
    }}
    .dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--green); }}
    main {{ padding: 24px 28px 34px; max-width: 1360px; margin: 0 auto; }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: end;
      gap: 18px;
      margin-bottom: 18px;
    }}
    h1 {{ margin: 0; font-size: 25px; line-height: 1.2; font-weight: 750; letter-spacing: 0; }}
    .lede {{ margin-top: 6px; color: var(--muted); max-width: 780px; }}
    .repo-card {{
      min-width: 280px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      padding: 12px 14px;
      box-shadow: var(--shadow);
    }}
    .repo-label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .05em; }}
    .repo-path {{ margin-top: 4px; font-size: 12px; color: #344054; overflow-wrap: anywhere; }}
    .grid {{ display: grid; gap: 14px; }}
    .metrics {{ grid-template-columns: repeat(6, minmax(150px, 1fr)); }}
    .analytics {{ grid-template-columns: minmax(280px, .8fr) minmax(0, 1.25fr) minmax(280px, .95fr); margin-top: 16px; }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    .metric {{
      min-height: 126px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .metric-top {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
    .metric-label {{ color: var(--muted); font-size: 12px; font-weight: 650; }}
    .metric-icon {{
      width: 30px;
      height: 30px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      color: #fff;
      font-size: 13px;
      font-weight: 800;
      background: var(--blue);
    }}
    .metric-icon.green {{ background: var(--green); }}
    .metric-icon.amber {{ background: var(--amber); }}
    .metric-icon.red {{ background: var(--red); }}
    .metric-value {{ margin-top: 14px; font-size: 34px; line-height: 1; font-weight: 760; font-variant-numeric: tabular-nums; }}
    .metric-note {{ color: var(--muted); font-size: 12px; }}
    .panel-header {{
      min-height: 52px;
      padding: 15px 16px 11px;
      border-bottom: 1px solid var(--line-soft);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    h2 {{ margin: 0; font-size: 14px; font-weight: 720; }}
    .panel-subtitle {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
    .panel-body {{ padding: 14px 16px 16px; }}
    .bar-row {{ display: grid; grid-template-columns: minmax(82px, 124px) 1fr 58px; align-items: center; gap: 11px; margin: 12px 0; }}
    .bar-label, .bar-value {{ color: #475467; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .bar-label {{ font-weight: 580; }}
    .bar-track {{ height: 9px; background: #eef2f6; border-radius: 999px; overflow: hidden; }}
    .bar-fill {{ height: 100%; background: var(--green); border-radius: 999px; min-width: 2px; }}
    .bar-fill.blue {{ background: var(--blue); }}
    .bar-fill.amber {{ background: var(--amber); }}
    .timeline {{ display: grid; grid-template-columns: repeat(14, 1fr); align-items: end; gap: 6px; height: 168px; padding-top: 8px; }}
    .day {{ display: grid; align-items: end; gap: 7px; min-width: 0; }}
    .day-bar {{ min-height: 3px; border-radius: 5px 5px 2px 2px; background: var(--blue); }}
    .day-label {{ color: var(--muted); font-size: 10px; text-align: center; white-space: nowrap; overflow: hidden; }}
    .tool-list {{ display: grid; gap: 10px; }}
    .tool-card {{
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      padding: 12px;
      background: var(--surface-2);
    }}
    .tool-row {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
    .tool-name {{ font-weight: 680; }}
    .tool-meta {{ margin-top: 5px; color: var(--muted); font-size: 12px; }}
    .table-panel {{ margin-top: 16px; overflow: hidden; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ padding: 12px 16px; border-bottom: 1px solid var(--line-soft); text-align: left; vertical-align: middle; }}
    th {{ color: var(--muted); background: var(--surface-2); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }}
    tr:last-child td {{ border-bottom: 0; }}
    td {{ overflow-wrap: anywhere; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .pill {{ display: inline-flex; align-items: center; height: 24px; padding: 0 8px; border-radius: 999px; background: #eef5ff; color: var(--blue); font-size: 12px; font-weight: 650; }}
    .pill.claude_code {{ background: #fff6e5; color: var(--amber); }}
    .pill.codex {{ background: #eaf8f2; color: var(--green); }}
    .pill.cursor {{ background: #eef5ff; color: var(--blue); }}
    .empty {{ color: var(--muted); padding: 18px 0; }}
    footer {{ color: var(--muted); margin-top: 14px; font-size: 12px; display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }}
    @media (max-width: 1100px) {{
      .metrics {{ grid-template-columns: repeat(3, minmax(150px, 1fr)); }}
      .analytics {{ grid-template-columns: 1fr; }}
      .hero {{ grid-template-columns: 1fr; }}
      .repo-card {{ min-width: 0; }}
    }}
    @media (max-width: 720px) {{
      .topbar, main {{ padding-left: 16px; padding-right: 16px; }}
      .top-actions {{ display: none; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .metric {{ min-height: 112px; }}
      .metric-value {{ font-size: 30px; }}
      .bar-row {{ grid-template-columns: 86px 1fr 44px; }}
      th:nth-child(1), td:nth-child(1), th:nth-child(5), td:nth-child(5) {{ display: none; }}
    }}
    @media (max-width: 480px) {{
      .metrics {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <nav class="topbar">
      <div class="brand">
        <div class="mark">AI</div>
        <div>
          <div class="brand-title">Attribution Console</div>
          <div class="brand-subtitle">{repo_label}</div>
        </div>
      </div>
      <div class="top-actions">
        <div class="status-pill"><span class="dot"></span><span id="live-status">Live local telemetry</span></div>
        <div class="status-pill" id="last-updated">Loading</div>
      </div>
    </nav>
    <main>
      <section class="hero">
        <div>
          <h1>AI usage analytics for engineering work</h1>
          <div class="lede">See how much AI-authored code activity is being captured from Codex, Claude Code, and Cursor before it becomes PR attribution data.</div>
        </div>
        <div class="repo-card">
          <div class="repo-label">Workspace</div>
          <div class="repo-path">{repo_label}</div>
        </div>
      </section>
      <section class="grid metrics">
        <div class="panel metric">
          <div class="metric-top"><div class="metric-label">Suggested</div><div class="metric-icon green">S</div></div>
          <div><div class="metric-value" id="suggested-lines">0</div><div class="metric-note">AI lines captured from tools</div></div>
        </div>
        <div class="panel metric">
          <div class="metric-top"><div class="metric-label">Still present</div><div class="metric-icon">A</div></div>
          <div><div class="metric-value" id="accepted-lines">0</div><div class="metric-note">AI lines still in workspace</div></div>
        </div>
        <div class="panel metric">
          <div class="metric-top"><div class="metric-label">Staged</div><div class="metric-icon amber">G</div></div>
          <div><div class="metric-value" id="staged-lines">0</div><div class="metric-note">AI lines ready to commit</div></div>
        </div>
        <div class="panel metric">
          <div class="metric-top"><div class="metric-label">Committed</div><div class="metric-icon green">C</div></div>
          <div><div class="metric-value" id="committed-lines">n/a</div><div class="metric-note">AI lines on this branch</div></div>
        </div>
        <div class="panel metric">
          <div class="metric-top"><div class="metric-label">Pushed</div><div class="metric-icon red">P</div></div>
          <div><div class="metric-value" id="pushed-status">n/a</div><div class="metric-note" id="pushed-note">No upstream branch</div></div>
        </div>
        <div class="panel metric">
          <div class="metric-top"><div class="metric-label">Touched</div><div class="metric-icon amber">F</div></div>
          <div><div class="metric-value" id="touched-files">0</div><div class="metric-note">Files with AI activity</div></div>
        </div>
      </section>
      <section class="grid analytics">
        <div class="panel">
          <div class="panel-header">
            <div><h2>Tool Mix</h2><div class="panel-subtitle">AI edit events and captured lines by source</div></div>
          </div>
          <div class="panel-body"><div class="tool-list" id="tool-cards"></div></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div><h2>Daily Activity</h2><div class="panel-subtitle">AI lines captured over the last 14 days</div></div>
          </div>
          <div class="panel-body"><div class="timeline" id="timeline"></div></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div><h2>File Hotspots</h2><div class="panel-subtitle">Files with the most AI-authored line activity</div></div>
          </div>
          <div class="panel-body"><div id="file-bars"></div></div>
        </div>
      </section>
      <section class="panel table-panel">
        <div class="panel-header">
          <div><h2>Recent AI Events</h2><div class="panel-subtitle">Latest captured AI edits by tool and file</div></div>
        </div>
      <table>
        <thead><tr><th>Time</th><th>Tool</th><th>File</th><th class="num">AI Lines</th><th>Source</th></tr></thead>
        <tbody id="recent"></tbody>
      </table>
      </section>
      <footer><span id="footer">Loading...</span><span>Raw code is not stored</span></footer>
    </main>
  </div>
  <script>
    const fmt = new Intl.NumberFormat();
    const toolColors = {{codex: 'green', cursor: 'blue', claude_code: 'amber'}};
    function esc(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    }}
    function setText(id, value) {{ document.getElementById(id).textContent = value; }}
    function bars(id, rows, labelKey, valueKey, tone = 'green') {{
      const el = document.getElementById(id);
      if (!rows.length) {{ el.innerHTML = '<div class="empty">No data yet.</div>'; return; }}
      const max = Math.max(...rows.map(row => row[valueKey]), 1);
      el.innerHTML = rows.map(row => `
        <div class="bar-row">
          <div class="bar-label" title="${{esc(row[labelKey])}}">${{esc(row[labelKey])}}</div>
          <div class="bar-track"><div class="bar-fill ${{tone}}" style="width:${{Math.max(3, (row[valueKey] / max) * 100)}}%"></div></div>
          <div class="bar-value num">${{fmt.format(row[valueKey])}}</div>
        </div>
      `).join('');
    }}
    function toolCards(data) {{
      const tools = Object.entries(data.lines_by_tool)
        .map(([tool, hashed_lines]) => ({{tool, hashed_lines, chunks: data.by_tool[tool] || 0}}))
        .sort((a, b) => b.hashed_lines - a.hashed_lines);
      const el = document.getElementById('tool-cards');
      if (!tools.length) {{ el.innerHTML = '<div class="empty">No data yet.</div>'; return; }}
      el.innerHTML = tools.map(row => `
        <div class="tool-card">
          <div class="tool-row"><span class="tool-name">${{esc(row.tool)}}</span><span class="pill ${{esc(row.tool)}}">${{fmt.format(row.hashed_lines)}} AI lines</span></div>
          <div class="tool-meta">${{fmt.format(row.chunks)}} edit events captured</div>
        </div>
      `).join('');
    }}
    function timeline(rows) {{
      const el = document.getElementById('timeline');
      if (!rows.length) {{ el.innerHTML = '<div class="empty">No activity yet.</div>'; return; }}
      const max = Math.max(...rows.map(row => row.hashed_lines), 1);
      el.innerHTML = rows.map(row => `
        <div class="day" title="${{esc(row.day)}} · ${{fmt.format(row.hashed_lines)}} AI lines">
          <div class="day-bar" style="height:${{Math.max(3, (row.hashed_lines / max) * 138)}}px"></div>
          <div class="day-label">${{esc(row.day.slice(5))}}</div>
        </div>
      `).join('');
    }}
    async function refresh() {{
      const data = await fetch('/api/summary', {{cache: 'no-store'}}).then(r => r.json());
      const k = data.kpis || {{}};
      setText('suggested-lines', fmt.format(k.suggested_lines || 0));
      setText('accepted-lines', fmt.format(k.present_in_workspace_lines || 0));
      setText('staged-lines', fmt.format(k.staged_ai_lines || 0));
      setText('committed-lines', k.committed_ai_lines === null || k.committed_ai_lines === undefined ? 'n/a' : fmt.format(k.committed_ai_lines));
      setText('pushed-status', k.push_status || 'n/a');
      setText('pushed-note', k.push_note || 'No upstream branch');
      setText('touched-files', fmt.format(k.touched_files || 0));
      toolCards(data);
      timeline(data.lines_by_day);
      bars('file-bars', data.top_files, 'file_path', 'hashed_lines', 'blue');
      document.getElementById('recent').innerHTML = data.recent_chunks.length ? data.recent_chunks.map(row => `
        <tr>
          <td>${{esc(row.event_time)}}</td>
          <td><span class="pill ${{esc(row.tool)}}">${{esc(row.tool)}}</span></td>
          <td>${{esc(row.file_path)}}</td>
          <td class="num">${{fmt.format(row.hashed_lines)}}</td>
          <td>${{esc(row.source)}}</td>
        </tr>
      `).join('') : '<tr><td colspan="5" class="empty">No chunks collected yet.</td></tr>';
      const updated = new Date().toLocaleTimeString();
      document.getElementById('footer').textContent = `Reading ${{data.events_file}}`;
      document.getElementById('last-updated').textContent = `Updated ${{updated}}`;
    }}
    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>
"""


def render_dashboard_html(repo: Path) -> str:
    repo_label = escape(str(repo))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Contribution Retention</title>
  <style>
    :root {{
      --bg: #f7f8fa;
      --surface: #ffffff;
      --ink: #101828;
      --muted: #667085;
      --line: #d8dee8;
      --green: #17845b;
      --blue: #315fbd;
      --amber: #b7791f;
      --shadow: 0 1px 2px rgba(16, 24, 40, .05), 0 14px 30px rgba(16, 24, 40, .06);
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0d1117;
        --surface: #161b22;
        --ink: #e6edf3;
        --muted: #8b949e;
        --line: #30363d;
        --green: #3fb950;
        --blue: #58a6ff;
        --amber: #d29922;
        --shadow: 0 1px 2px rgba(0,0,0,.3), 0 14px 30px rgba(0,0,0,.2);
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .topbar {{
      height: 56px;
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 0 28px;
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }}
    .mark {{
      width: 30px;
      height: 30px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      background: #344054;
      color: #fff;
      font-weight: 800;
      font-size: 12px;
    }}
    .brand {{ min-width: 0; flex: 1; }}
    .brand strong {{ display: block; font-size: 14px; }}
    .brand span {{ display: block; color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 66vw; }}
    .refresh-btn {{
      flex-shrink: 0;
      height: 32px;
      padding: 0 14px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface);
      color: var(--ink);
      font-size: 13px;
      cursor: pointer;
    }}
    .refresh-btn:hover {{ background: var(--bg); }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 34px 28px; }}
    .hero {{
      display: grid;
      grid-template-columns: 320px minmax(420px, 1fr);
      gap: 18px;
      align-items: stretch;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    .score {{ padding: 26px; display: grid; align-content: center; justify-items: center; text-align: center; }}
    .eyebrow {{ color: var(--muted); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }}
    h1 {{ margin: 10px 0 0; font-size: 22px; letter-spacing: 0; }}
    .percent {{
      --pct: 0%;
      width: 190px;
      height: 190px;
      margin-top: 22px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: radial-gradient(circle at center, var(--surface) 0 61%, transparent 62%), conic-gradient(var(--green) var(--pct), #edf1f5 0);
      color: var(--ink);
      font-size: 48px;
      line-height: 1;
      font-weight: 800;
      letter-spacing: -1px;
      font-variant-numeric: tabular-nums;
    }}
    .score-note {{ margin-top: 16px; color: var(--muted); font-size: 14px; max-width: 260px; }}
    .flow {{ padding: 24px; display: flex; flex-direction: column; justify-content: center; }}
    .flow-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; align-items: stretch; }}
    .flow-box {{ border: 1px solid var(--line); border-radius: 8px; padding: 16px; min-height: 110px; }}
    .flow-label {{ color: var(--muted); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }}
    .flow-value {{ margin-top: 8px; font-size: 36px; line-height: 1; font-weight: 760; font-variant-numeric: tabular-nums; }}
    .flow-copy {{ margin-top: 8px; color: var(--muted); font-size: 13px; }}
    .bar {{ margin-top: 22px; height: 12px; background: #edf1f5; border-radius: 999px; overflow: hidden; }}
    .bar-fill {{ height: 100%; width: 0; background: var(--green); border-radius: 999px; transition: width .25s ease; }}
    .meta-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 18px; }}
    .mini {{ padding: 16px; }}
    .mini-value {{ margin-top: 6px; font-size: 28px; font-weight: 760; font-variant-numeric: tabular-nums; }}
    .section {{ margin-top: 18px; padding: 18px; }}
    .section-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: baseline; margin-bottom: 14px; }}
    h2 {{ margin: 0; font-size: 15px; }}
    .section-sub {{ color: var(--muted); font-size: 12px; }}
    .tool-list {{ display: grid; gap: 10px; }}
    .tool-row {{ display: grid; grid-template-columns: 140px 1fr 72px; gap: 12px; align-items: center; }}
    .tool-name {{ font-weight: 680; }}
    .track {{ height: 9px; background: #edf1f5; border-radius: 999px; overflow: hidden; }}
    .fill {{ height: 100%; background: var(--blue); border-radius: 999px; }}
    .number {{ text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }}
    .details {{ display: grid; grid-template-columns: .8fr 1fr; gap: 14px; margin-top: 18px; }}
    .check-list {{ display: grid; gap: 10px; }}
    .check-row {{ display: grid; grid-template-columns: 22px 1fr auto; gap: 10px; align-items: start; }}
    .check-dot {{ width: 18px; height: 18px; border-radius: 50%; display: grid; place-items: center; font-size: 11px; color: #fff; background: var(--green); margin-top: 1px; }}
    .check-dot.warn {{ background: var(--amber); }}
    .check-title {{ font-weight: 650; }}
    .check-detail {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
    .check-state {{ color: var(--muted); font-size: 12px; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }}
    th {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }}
    td {{ overflow-wrap: anywhere; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .wide {{ grid-column: 1 / -1; }}
    footer {{ margin-top: 14px; color: var(--muted); font-size: 12px; display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
    @media (max-width: 850px) {{
      main {{ padding: 24px 16px; }}
      .hero {{ grid-template-columns: 1fr; }}
      .flow-row {{ grid-template-columns: repeat(2, 1fr); }}
      .meta-grid {{ grid-template-columns: 1fr; }}
      .details {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <nav class="topbar">
    <div class="mark">CR</div>
    <div class="brand"><strong>Contribution Retention</strong><span>{repo_label}</span></div>
    <button class="refresh-btn" onclick="refresh()" title="Refresh now">↻ Refresh</button>
  </nav>
  <main>
    <section class="hero">
      <div class="card score">
        <div class="eyebrow">Merge-ready contribution</div>
        <h1>Generated lines retained in the candidate</h1>
        <div class="percent" id="merge-percent">0%</div>
        <div class="score-note" id="merge-note">Waiting for telemetry...</div>
      </div>
      <div class="card flow">
        <div class="flow-row">
          <div class="flow-box">
            <div class="flow-label">Generated</div>
            <div class="flow-value" id="created-lines">0</div>
            <div class="flow-copy">Lines captured from coding tools</div>
          </div>
          <div class="flow-box">
            <div class="flow-label" id="survived-label">Survived</div>
            <div class="flow-value" id="merged-lines">0</div>
            <div class="flow-copy" id="survived-copy">Same lines still present</div>
          </div>
          <div class="flow-box">
            <div class="flow-label">Staged</div>
            <div class="flow-value" id="staged-lines">0</div>
            <div class="flow-copy">Ready to commit</div>
          </div>
          <div class="flow-box">
            <div class="flow-label">Files</div>
            <div class="flow-value" id="touched-files">0</div>
            <div class="flow-copy">Touched by generated changes</div>
          </div>
        </div>
        <div class="bar"><div class="bar-fill" id="merge-bar"></div></div>
      </div>
    </section>
    <section class="meta-grid">
      <div class="card mini"><div class="eyebrow">Delivery state</div><div class="mini-value" id="delivery-state">Workspace</div><div class="flow-copy" id="delivery-note">Current working tree candidate</div></div>
      <div class="card mini"><div class="eyebrow">Push state</div><div class="mini-value" id="push-status">n/a</div><div class="flow-copy" id="push-note">No upstream branch</div></div>
      <div class="card mini"><div class="eyebrow">Review signal</div><div class="mini-value" id="review-signal">n/a</div><div class="flow-copy">Retention of generated contribution</div></div>
    </section>
    <section class="card section">
      <div class="section-head">
        <div><h2>Source mix</h2><div class="section-sub">Generated contribution by coding tool</div></div>
        <div class="section-sub" id="last-updated">Loading</div>
      </div>
      <div class="tool-list" id="tool-list"></div>
    </section>
    <section class="details">
      <div class="card section">
        <div class="section-head">
          <div><h2>Readiness</h2><div class="section-sub">Can this repo produce PR metrics?</div></div>
        </div>
        <div class="check-list" id="readiness-list"></div>
      </div>
      <div class="card section">
        <div class="section-head">
          <div><h2>Retention by tool</h2><div class="section-sub">Generated lines that survived by source</div></div>
        </div>
        <div id="tool-retention"></div>
      </div>
      <div class="card section wide">
        <div class="section-head">
          <div><h2>Retention by file</h2><div class="section-sub">Files where generated lines survived into the candidate</div></div>
        </div>
        <div id="file-retention"></div>
      </div>
    </section>
    <footer><span id="footer">Reading local telemetry</span><span>Raw code is not stored</span></footer>
  </main>
  <script>
    const fmt = new Intl.NumberFormat();
    const TOOL_LABELS = {{claude_code: 'Claude Code', cursor: 'Cursor', codex: 'Codex'}};
    function toolLabel(tool) {{ return TOOL_LABELS[tool] || tool; }}
    function esc(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    }}
    function setText(id, value) {{ document.getElementById(id).textContent = value; }}
    function basisText(basis) {{
      if (basis === 'branch') return ['Committed', 'Same generated lines on this branch', 'Branch diff'];
      if (basis === 'workspace') return ['Retained', 'Same generated lines still in workspace', 'Workspace'];
      return ['Unavailable', 'Git base unavailable'];
    }}
    function renderTools(data) {{
      const rows = Object.entries(data.lines_by_tool || {{}})
        .map(([tool, lines]) => ({{tool, lines}}))
        .sort((a, b) => b.lines - a.lines);
      const el = document.getElementById('tool-list');
      if (!rows.length) {{ el.innerHTML = '<div class="section-sub">No generated contribution captured yet.</div>'; return; }}
      const max = Math.max(...rows.map(row => row.lines), 1);
      el.innerHTML = rows.map(row => `
        <div class="tool-row">
          <div class="tool-name">${{esc(toolLabel(row.tool))}}</div>
          <div class="track"><div class="fill" style="width:${{Math.max(3, row.lines / max * 100)}}%"></div></div>
          <div class="number">${{fmt.format(row.lines)}}</div>
        </div>
      `).join('');
    }}
    function renderReadiness(rows) {{
      const el = document.getElementById('readiness-list');
      if (!rows.length) {{ el.innerHTML = '<div class="section-sub">No checks available.</div>'; return; }}
      el.innerHTML = rows.map(row => `
        <div class="check-row">
          <div class="check-dot ${{row.ok ? '' : 'warn'}}">${{row.ok ? '✓' : '!'}}</div>
          <div><div class="check-title">${{esc(row.label)}}</div><div class="check-detail">${{esc(row.detail)}}</div></div>
          <div class="check-state">${{row.ok ? 'Ready' : 'Check'}}</div>
        </div>
      `).join('');
    }}
    function retentionTable(id, rows, nameKey) {{
      const el = document.getElementById(id);
      if (!rows.length) {{ el.innerHTML = '<div class="section-sub">No retained contribution yet.</div>'; return; }}
      el.innerHTML = `
        <table>
          <thead><tr><th>${{nameKey === 'tool' ? 'Tool' : 'File'}}</th><th class="num">Generated</th><th class="num">Retained</th><th class="num">%</th></tr></thead>
          <tbody>
            ${{rows.map(row => `
              <tr>
                <td>${{esc(nameKey === 'tool' ? toolLabel(row[nameKey]) : row[nameKey])}}</td>
                <td class="num">${{fmt.format(row.generated)}}</td>
                <td class="num">${{fmt.format(row.retained)}}</td>
                <td class="num">${{Number(row.percent || 0).toFixed(1)}}%</td>
              </tr>
            `).join('')}}
          </tbody>
        </table>
      `;
    }}
    async function refresh() {{
      const data = await fetch('/api/summary', {{cache: 'no-store'}}).then(r => r.json());
      const k = data.kpis || {{}};
      const percent = Number(k.merge_percent || 0);
      const basis = basisText(k.merge_basis);
      setText('merge-percent', `${{percent.toFixed(1)}}%`);
      setText('created-lines', fmt.format(k.suggested_lines || 0));
      setText('merged-lines', fmt.format(k.merged_ai_lines || 0));
      setText('survived-label', basis[0]);
      setText('survived-copy', basis[1]);
      setText('merge-note', `${{fmt.format(k.merged_ai_lines || 0)}} of ${{fmt.format(k.suggested_lines || 0)}} generated lines matched again.`);
      setText('staged-lines', fmt.format(k.staged_ai_lines || 0));
      setText('delivery-state', basis[2] || 'n/a');
      setText('delivery-note', basis[1] || 'No delivery base available');
      setText('push-status', k.push_status || 'n/a');
      setText('push-note', k.push_note || 'No upstream branch');
      setText('touched-files', fmt.format(k.touched_files || 0));
      setText('review-signal', percent >= 70 ? 'High' : percent >= 35 ? 'Medium' : 'Low');
      document.getElementById('merge-bar').style.width = `${{Math.max(0, Math.min(100, percent))}}%`;
      document.getElementById('merge-percent').style.setProperty('--pct', `${{Math.max(0, Math.min(100, percent))}}%`);
      renderTools(data);
      renderReadiness(data.readiness || []);
      retentionTable('tool-retention', data.retention_by_tool || [], 'tool');
      retentionTable('file-retention', data.retention_by_file || [], 'file_path');
      setText('last-updated', `Updated ${{new Date().toLocaleTimeString()}}`);
      setText('footer', `Reading ${{data.events_file}}`);
    }}
    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>
"""


TOOL_LABELS: dict[str, str] = {
    "claude_code": "Claude Code",
    "cursor": "Cursor",
    "codex": "Codex",
}


def tool_label(tool: str) -> str:
    return TOOL_LABELS.get(tool, tool)


def _chunk_row(chunk: AiCodeChunk) -> dict:
    return {
        "event_time": chunk.event_time,
        "tool": chunk.tool,
        "tool_label": tool_label(chunk.tool),
        "file_path": chunk.file_path,
        "hashed_lines": len(chunk.line_hashes),
        "source": chunk.metadata.get("source") or chunk.metadata.get("hook_event_name") or chunk.metadata.get("edit_source") or "",
    }


def _readiness(events_file: Path, repo: Path | None, chunks: list[AiCodeChunk]) -> list[dict]:
    repo_path = repo.resolve() if repo else None
    checks = [
        {
            "label": "Telemetry collected",
            "ok": events_file.exists() and len(chunks) > 0,
            "detail": f"{len(chunks)} events in local telemetry",
        }
    ]
    if not repo_path:
        checks.append({"label": "Git repository", "ok": False, "detail": "No repository context"})
        return checks
    checks.extend(
        [
            {
                "label": "Claude Code hooks",
                "ok": (repo_path / ".claude/settings.json").exists(),
                "detail": ".claude/settings.json",
            },
            {
                "label": "Cursor hooks",
                "ok": (repo_path / ".cursor/hooks.json").exists(),
                "detail": ".cursor/hooks.json",
            },
            {
                "label": "Collector config",
                "ok": (repo_path / ".ai-use/config.json").exists(),
                "detail": "Needed for pushed PR metrics",
            },
            {
                "label": "Pre-push uploader",
                "ok": (repo_path / ".git/hooks/pre-push").exists(),
                "detail": "Uploads hash-only telemetry outside PR diff",
            },
            {
                "label": "Upstream branch",
                "ok": run_git(repo_path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]) is not None,
                "detail": "Needed for pushed/branch comparison",
            },
        ]
    )
    return checks


def _retention_breakdowns(chunks: list[AiCodeChunk], repo: Path | None) -> dict:
    retained_hashes = _retained_hashes(repo.resolve(), chunks) if repo else Counter()
    by_tool: dict[str, dict[str, int | str | float]] = {}
    by_file: dict[str, dict[str, int | str | float]] = {}
    for chunk in chunks:
        for line_hash in chunk.line_hashes:
            retained = retained_hashes[line_hash] > 0
            if retained:
                retained_hashes[line_hash] -= 1
            tool_row = by_tool.setdefault(chunk.tool, {"tool": chunk.tool, "generated": 0, "retained": 0, "percent": 0.0})
            tool_row["generated"] = int(tool_row["generated"]) + 1
            if retained:
                tool_row["retained"] = int(tool_row["retained"]) + 1
            file_row = by_file.setdefault(
                chunk.file_path,
                {"file_path": chunk.file_path, "generated": 0, "retained": 0, "percent": 0.0},
            )
            file_row["generated"] = int(file_row["generated"]) + 1
            if retained:
                file_row["retained"] = int(file_row["retained"]) + 1

    for rows in (by_tool.values(), by_file.values()):
        for row in rows:
            row["percent"] = _percent(int(row["retained"]), int(row["generated"]))
    return {
        "by_tool": sorted(by_tool.values(), key=lambda row: (-int(row["generated"]), str(row["tool"]))),
        "by_file": sorted(by_file.values(), key=lambda row: (-int(row["generated"]), str(row["file_path"])))[:12],
    }


def _retained_hashes(repo: Path, chunks: list[AiCodeChunk]) -> Counter[str]:
    files = {chunk.file_path for chunk in chunks if chunk.file_path and chunk.file_path != "unknown"}
    retained: Counter[str] = Counter()
    for file_path in files:
        path = repo / file_path
        if not path.exists() or not path.is_file():
            continue
        try:
            retained.update(hash_line(line) for line in path.read_text(encoding="utf-8", errors="ignore").splitlines())
        except OSError:
            continue
    return retained


def _build_kpis(chunks: list[AiCodeChunk], repo: Path | None) -> dict:
    suggested_lines = sum(len(chunk.line_hashes) for chunk in chunks)
    touched_files = len({chunk.file_path for chunk in chunks if chunk.file_path and chunk.file_path != "unknown"})
    if repo is None:
        merged_lines = 0
        return {
            "suggested_lines": suggested_lines,
            "present_in_workspace_lines": 0,
            "staged_ai_lines": 0,
            "committed_ai_lines": None,
            "pushed_ai_lines": None,
            "merged_ai_lines": merged_lines,
            "merge_percent": _percent(merged_lines, suggested_lines),
            "merge_basis": "unavailable",
            "push_status": "n/a",
            "push_note": "Git workspace unavailable",
            "touched_files": touched_files,
        }

    repo = repo.resolve()
    upstream = run_git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    ahead_behind = run_git(repo, ["rev-list", "--left-right", "--count", "HEAD...@{u}"]) if upstream else None
    ahead = behind = None
    if ahead_behind:
        parts = ahead_behind.split()
        if len(parts) == 2:
            ahead, behind = int(parts[0]), int(parts[1])

    branch_base = _branch_base(repo, upstream)
    committed = _ai_lines_in_git_diff(repo, chunks, [f"{branch_base}...HEAD"]) if branch_base else None
    pushed = _ai_lines_in_git_diff(repo, chunks, [f"{branch_base}...{upstream}"]) if branch_base and upstream else None
    present = _present_in_workspace_lines(repo, chunks)
    merged_lines = committed if committed is not None else present

    return {
        "suggested_lines": suggested_lines,
        "present_in_workspace_lines": present,
        "staged_ai_lines": _ai_lines_in_git_diff(repo, chunks, ["--cached"]),
        "committed_ai_lines": committed,
        "pushed_ai_lines": pushed,
        "merged_ai_lines": merged_lines,
        "merge_percent": _percent(merged_lines, suggested_lines),
        "merge_basis": "branch" if committed is not None else "workspace",
        "push_status": _push_status(upstream, ahead, behind),
        "push_note": _push_note(upstream, ahead, behind, pushed),
        "touched_files": touched_files,
    }


def _present_in_workspace_lines(repo: Path, chunks: list[AiCodeChunk]) -> int:
    expected: dict[str, Counter[str]] = {}
    for chunk in chunks:
        if not chunk.file_path or chunk.file_path == "unknown":
            continue
        expected.setdefault(chunk.file_path, Counter()).update(chunk.line_hashes)

    present = 0
    for file_path, hashes in expected.items():
        path = repo / file_path
        if not path.exists() or not path.is_file():
            continue
        try:
            current_hashes = [hash_line(line) for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()]
        except OSError:
            continue
        remaining = hashes.copy()
        for line_hash in current_hashes:
            if remaining[line_hash] > 0:
                present += 1
                remaining[line_hash] -= 1
    return present


def _ai_lines_in_git_diff(repo: Path, chunks: list[AiCodeChunk], diff_args: list[str]) -> int:
    diff = run_git(repo, ["diff", "--unified=0", *diff_args])
    if not diff:
        return 0
    attributions = attribute_lines(parse_unified_diff(diff), chunks)
    return summarize(attributions).attributed_lines


def _branch_base(repo: Path, upstream: str | None) -> str | None:
    candidates = []
    if upstream:
        candidates.append(upstream)
    candidates.extend(["origin/main", "origin/master", "main", "master"])
    for candidate in candidates:
        base = run_git(repo, ["merge-base", "HEAD", candidate])
        if base:
            return base
    return None


def _push_status(upstream: str | None, ahead: int | None, behind: int | None) -> str:
    if not upstream:
        return "No upstream"
    if ahead == 0 and behind == 0:
        return "Synced"
    if ahead and ahead > 0:
        return f"{ahead} ahead"
    if behind and behind > 0:
        return f"{behind} behind"
    return "Unknown"


def _push_note(upstream: str | None, ahead: int | None, behind: int | None, pushed: int | None) -> str:
    if not upstream:
        return "Set upstream to measure pushed generated lines"
    pushed_text = "n/a" if pushed is None else str(pushed)
    if ahead and ahead > 0:
        return f"{ahead} local commits not pushed · {pushed_text} generated lines already upstream"
    if behind and behind > 0:
        return f"Behind upstream · {pushed_text} generated lines upstream"
    return f"Upstream synced · {pushed_text} generated lines pushed"


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _day(value: str) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10] if len(value) >= 10 else None
