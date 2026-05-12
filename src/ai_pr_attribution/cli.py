from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from ai_pr_attribution.adapters import chunk_from_hook_payload, parse_hook_stdin
from ai_pr_attribution.codex_session import import_codex_session, latest_codex_session
from ai_pr_attribution.collector_server import serve
from ai_pr_attribution.dashboard import serve_dashboard
from ai_pr_attribution.diff_parser import parse_unified_diff
from ai_pr_attribution.events import DEFAULT_EVENTS_PATH, append_chunk, read_chunks
from ai_pr_attribution.git_utils import repo_id
from ai_pr_attribution.github import upsert_check_run, upsert_pr_comment
from ai_pr_attribution.installer import install_all, install_github_native, install_hooks
from ai_pr_attribution.matcher import attribute_lines, summarize
from ai_pr_attribution.report import render_check_run, render_markdown, summary_to_json
from ai_pr_attribution.schema import ToolName
from ai_pr_attribution.telemetry_client import fetch_telemetry, upload_telemetry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai-pr-attribution")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="Install collection hooks for this repo.")
    install.add_argument("--repo", type=Path, default=Path.cwd())
    install.add_argument("--commit", action="store_true",
                         help="Commit and push installed files automatically.")
    install.add_argument("--collector-url", help=argparse.SUPPRESS)
    install.add_argument("--collector-token", help=argparse.SUPPRESS)

    install_hooks_parser = subparsers.add_parser("install-hooks", help="Backward-compatible alias for install.")
    install_hooks_parser.add_argument("--repo", type=Path, default=Path.cwd())
    install_hooks_parser.add_argument("--collector-url")
    install_hooks_parser.add_argument("--collector-token")

    collect = subparsers.add_parser("collect-hook")
    collect.add_argument("--tool", choices=["cursor", "claude_code", "codex"], required=True)
    collect.add_argument("--repo", type=Path, default=Path.cwd())
    collect.add_argument("--events-file", type=Path)

    analyze = subparsers.add_parser("analyze-pr")
    analyze.add_argument("--repo", type=Path, default=Path.cwd())
    analyze.add_argument("--diff-file", type=Path)
    analyze.add_argument("--diff-url")
    analyze.add_argument("--events-file", type=Path)
    analyze.add_argument("--format", choices=["markdown", "json"], default="markdown")
    analyze.add_argument("--output", type=Path)
    analyze.add_argument("--post-comment", action="store_true",
                         help="Post a PR comment (deprecated — use --post-check).")
    analyze.add_argument("--post-check", action="store_true",
                         help="Post a GitHub Check Run with the attribution result.")
    analyze.add_argument("--final", action="store_true",
                         help="Mark this as the final score (posted at merge time).")
    analyze.add_argument("--collector-url")
    analyze.add_argument("--collector-token")
    analyze.add_argument("--commit-sha")
    analyze.add_argument("--repo-id")
    analyze.add_argument("--github-native", action="store_true",
                         help="Fetch events from refs/ai-attribution/* before analyzing.")

    codex = subparsers.add_parser("import-codex-session")
    codex.add_argument("--repo", type=Path, default=Path.cwd())
    codex.add_argument("--session-file", type=Path)
    codex.add_argument("--events-file", type=Path)

    upload_ref_cmd = subparsers.add_parser("upload-ref",
                                           help="Push local events to refs/ai-attribution/<user>.")
    upload_ref_cmd.add_argument("--repo", type=Path, default=Path.cwd())
    upload_ref_cmd.add_argument("--events-file", type=Path)

    upload = subparsers.add_parser("upload-telemetry")
    upload.add_argument("--repo", type=Path, default=Path.cwd())
    upload.add_argument("--events-file", type=Path)
    upload.add_argument("--collector-url")
    upload.add_argument("--collector-token")

    fetch = subparsers.add_parser("fetch-telemetry")
    fetch.add_argument("--repo", type=Path, default=Path.cwd())
    fetch.add_argument("--output", type=Path, default=Path(".ai-pr-attribution/fetched-events.ndjson"))
    fetch.add_argument("--collector-url")
    fetch.add_argument("--collector-token")
    fetch.add_argument("--commit-sha")
    fetch.add_argument("--repo-id")
    fetch.add_argument("--github-native", action="store_true",
                       help="Fetch events from refs/ai-attribution/* instead of a collector.")

    server = subparsers.add_parser("serve-collector")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--db", type=Path, default=Path(".ai-pr-attribution/collector.sqlite3"))
    server.add_argument("--token")

    dashboard = subparsers.add_parser("dashboard", help="Run the local usage dashboard.")
    dashboard.add_argument("--repo", type=Path, default=Path.cwd())
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8787)
    dashboard.add_argument("--events-file", type=Path)

    render_dash = subparsers.add_parser("render-dashboard",
                                        help="Render the project-wide dashboard as markdown.")
    render_dash.add_argument("--repo", type=Path, default=Path.cwd())
    render_dash.add_argument("--events-file", type=Path)
    render_dash.add_argument("--output", type=Path, default=Path("docs/AI_USAGE.md"))
    render_dash.add_argument("--github-native", action="store_true",
                             help="Fetch events from refs/ai-attribution/* before rendering.")

    args = parser.parse_args(argv)
    if args.command == "install":
        if args.collector_url or args.collector_token:
            return _install(args.repo, args.collector_url, args.collector_token)
        return _install_github_native(args.repo, commit=args.commit)
    if args.command == "install-hooks":
        return _install(args.repo, args.collector_url, args.collector_token)
    if args.command == "collect-hook":
        return _collect(args.tool, args.repo, args.events_file)
    if args.command == "analyze-pr":
        return _analyze(args)
    if args.command == "import-codex-session":
        return _import_codex_session(args.repo, args.session_file, args.events_file)
    if args.command == "upload-ref":
        return _upload_ref(args.repo, args.events_file)
    if args.command == "upload-telemetry":
        return _upload_telemetry(args.repo, args.events_file, args.collector_url, args.collector_token)
    if args.command == "fetch-telemetry":
        return _fetch_telemetry(args)
    if args.command == "serve-collector":
        serve(args.host, args.port, args.db, args.token)
        return 0
    if args.command == "dashboard":
        serve_dashboard(args.repo, args.host, args.port, args.events_file)
        return 0
    if args.command == "render-dashboard":
        return _render_dashboard(args)
    raise AssertionError(args.command)


def _render_dashboard(args) -> int:
    from ai_pr_attribution.dashboard_markdown import render_dashboard_markdown
    repo = args.repo.resolve()
    events_file = args.events_file or repo / DEFAULT_EVENTS_PATH

    if getattr(args, "github_native", False):
        from ai_pr_attribution.github_native import download_events
        fetched = repo / ".ai-pr-attribution/fetched-events.ndjson"
        download_events(fetched, repo)
        events_file = fetched

    markdown = render_dashboard_markdown(events_file, repo=repo)
    output = args.output if args.output.is_absolute() else repo / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    print(f"Wrote {output}")
    return 0


def _install(repo: Path, collector_url: str | None, collector_token: str | None) -> int:
    created = install_all(repo, collector_url=collector_url, collector_token=collector_token)
    print("AI attribution installed.")
    for path in created:
        print(f"  {path}")
    print("\nClaude Code and Cursor will collect through their repo hook configs.")
    print("Codex Desktop edits will be imported automatically before git commits.")
    if collector_url:
        print("Hash-only telemetry will upload automatically before git pushes.")
    else:
        print("Set a collector later with: ai-pr-attribution install --collector-url https://collector.example")
    return 0


def _install_github_native(repo: Path, commit: bool = False) -> int:
    import subprocess
    created = install_github_native(repo)
    print("AI attribution installed.")
    for path in created:
        print(f"  {path}")
    if commit:
        repo = repo.resolve()
        files = [str(p) for p in created if p.exists()]
        subprocess.run(["git", "-C", str(repo), "add"] + files, check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", "chore: add AI PR attribution hooks and workflow"], check=True)
        result = subprocess.run(["git", "-C", str(repo), "push"], capture_output=True)
        if result.returncode == 0:
            print("\nCommitted and pushed.")
        else:
            print("\nCommitted. Push manually when your remote is configured:")
            print("  git push")
    else:
        print("\nCommit and push to activate:")
        print("  git add .ai-pr-attribution .github/workflows/ai-pr-attribution.yml .cursor .claude")
        print("  git commit -m 'chore: add AI PR attribution'")
        print("  git push")
    return 0


def _collect(tool: ToolName, repo: Path, events_file: Path | None) -> int:
    repo = repo.resolve()
    payload = parse_hook_stdin(sys.stdin.read())
    chunk = chunk_from_hook_payload(tool, repo, payload)
    target = events_file or repo / DEFAULT_EVENTS_PATH
    append_chunk(target, chunk)
    print(json.dumps({"chunk_id": chunk.chunk_id, "line_hashes": len(chunk.line_hashes), "events_file": str(target)}))
    return 0


def _analyze(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    events_file = args.events_file or repo / DEFAULT_EVENTS_PATH

    if getattr(args, "github_native", False):
        from ai_pr_attribution.github_native import download_events
        fetched = repo / ".ai-pr-attribution/fetched-events.ndjson"
        download_events(fetched, repo)
        events_file = fetched
    elif args.collector_url or os.environ.get("AI_ATTRIBUTION_COLLECTOR_URL"):
        events_file = repo / ".ai-pr-attribution/fetched-events.ndjson"
        fetch_telemetry(
            repo,
            events_file,
            url=args.collector_url,
            token=args.collector_token,
            repo_value=args.repo_id,
            commit_sha=args.commit_sha,
        )

    diff_text = _load_diff(args.diff_file, args.diff_url)
    chunks = read_chunks(events_file)
    added_lines = parse_unified_diff(diff_text)
    attributions = attribute_lines(added_lines, chunks)
    summary = summarize(attributions)

    if args.format == "json":
        output = summary_to_json(summary)
    else:
        output = render_markdown(summary, attributions)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + ("\n" if not output.endswith("\n") else ""), encoding="utf-8")
    else:
        print(output)

    final = getattr(args, "final", False)
    if args.post_check:
        if not args.commit_sha:
            raise SystemExit("--post-check requires --commit-sha")
        title, body = render_check_run(summary, attributions, final=final)
        upsert_check_run(args.commit_sha, title, body)
    if args.post_comment:
        upsert_pr_comment(render_markdown(summary, attributions, final=final))
    return 0


def _upload_ref(repo: Path, events_file: Path | None) -> int:
    from ai_pr_attribution.github_native import upload_events
    repo = repo.resolve()
    target = events_file or repo / DEFAULT_EVENTS_PATH
    count = upload_events(target, repo)
    print(json.dumps({"lines_uploaded": count}))
    return 0


def _import_codex_session(repo: Path, session_file: Path | None, events_file: Path | None) -> int:
    repo = repo.resolve()
    session = session_file or latest_codex_session()
    if not session:
        raise SystemExit("no Codex session file found under ~/.codex/sessions")
    target = events_file or repo / DEFAULT_EVENTS_PATH
    count = import_codex_session(session, repo, target)
    print(json.dumps({"imported_chunks": count, "session_file": str(session), "events_file": str(target)}))
    return 0


def _upload_telemetry(repo: Path, events_file: Path | None, collector_url: str | None, collector_token: str | None) -> int:
    repo = repo.resolve()
    target = events_file or repo / DEFAULT_EVENTS_PATH
    result = upload_telemetry(repo, target, url=collector_url, token=collector_token)
    print(json.dumps(result, sort_keys=True))
    return 0


def _fetch_telemetry(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    if getattr(args, "github_native", False):
        from ai_pr_attribution.github_native import download_events
        count = download_events(args.output, repo)
        print(json.dumps({"chunks": count, "events_file": str(args.output)}, sort_keys=True))
        return 0
    chunks = fetch_telemetry(
        repo,
        args.output,
        url=args.collector_url,
        token=args.collector_token,
        repo_value=args.repo_id,
        commit_sha=args.commit_sha,
    )
    print(json.dumps({"chunks": len(chunks), "events_file": str(args.output)}, sort_keys=True))
    return 0


def _load_diff(diff_file: Path | None, diff_url: str | None) -> str:
    if diff_file:
        return diff_file.read_text(encoding="utf-8")
    url = diff_url or os.environ.get("PR_DIFF_URL")
    if not url:
        raise SystemExit("provide --diff-file, --diff-url, or PR_DIFF_URL")
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3.diff"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
