from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


class UserEmailMissingError(RuntimeError):
    """Raised when git user.email is not configured.

    We refuse to push attribution events under a default "unknown" identity
    because every misconfigured machine would collapse onto the same ref and
    silently overwrite each other's data.
    """


def _user_ref(repo: Path) -> str:
    """Return a stable per-developer ref name derived from git user.email.

    Raises UserEmailMissingError if git user.email is not set, so we never
    silently collapse multiple developers onto the same "unknown" ref.
    Uses a 16-hex-char prefix of sha256(email) — collision probability is
    negligible for any realistic org size.
    """
    result = _git("config", "user.email", cwd=repo, check=False)
    email = result.stdout.strip()
    if not email:
        raise UserEmailMissingError(
            "git user.email is not configured. Set it with:\n"
            "  git config --global user.email you@example.com\n"
            "Without an email, attribution events would collide with other "
            "developers' refs and silently overwrite each other."
        )
    user_hash = hashlib.sha256(email.encode()).hexdigest()[:16]
    return f"refs/ai-attribution/{user_hash}"


def upload_events(events_file: Path, repo: Path) -> int:
    """Store events file as a git blob and push to refs/ai-attribution/<user>.

    Returns 0 (no-op) on any expected failure — missing file, missing
    user.email, push rejected — without crashing the calling git hook.
    """
    if not events_file.exists():
        return 0
    content = events_file.read_text(encoding="utf-8").strip()
    if not content:
        return 0

    try:
        ref = _user_ref(repo)
    except UserEmailMissingError as exc:
        print(f"ai-use: {exc}", file=sys.stderr)
        return 0

    # Write the file as a git blob object
    result = _git("hash-object", "-w", str(events_file), cwd=repo)
    blob_sha = result.stdout.strip()

    try:
        _git("push", "origin", f"{blob_sha}:{ref}", "--force", cwd=repo)
    except subprocess.CalledProcessError as exc:
        print(f"ai-use: failed to push events ref: {exc.stderr}", file=sys.stderr)
        return 0

    return content.count("\n") + 1


def download_events(output: Path, repo: Path) -> int:
    """Fetch all refs/ai-attribution/* and concatenate into output."""
    _git("fetch", "origin", "+refs/ai-attribution/*:refs/ai-attribution/*",
         cwd=repo, check=False)

    result = _git("for-each-ref", "--format=%(refname)", "refs/ai-attribution/",
                  cwd=repo, check=False)
    refs = [r.strip() for r in result.stdout.splitlines() if r.strip()]
    if not refs:
        return 0

    chunks: list[str] = []
    for ref in refs:
        blob = _git("cat-file", "blob", ref, cwd=repo, check=False)
        if blob.returncode == 0 and blob.stdout.strip():
            chunks.append(blob.stdout.strip())

    if not chunks:
        return 0

    content = "\n".join(chunks)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content + "\n", encoding="utf-8")
    return content.count("\n") + 1
