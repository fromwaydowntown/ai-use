from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(".ai-pr-attribution/config.json")


def write_config(repo: Path, values: dict[str, Any]) -> Path:
    path = repo.resolve() / CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_config(repo)
    existing.update({key: value for key, value in values.items() if value is not None})
    path.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_config(repo: Path) -> dict[str, Any]:
    path = repo.resolve() / CONFIG_PATH
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def collector_url(repo: Path) -> str | None:
    return os.environ.get("AI_ATTRIBUTION_COLLECTOR_URL") or read_config(repo).get("collector_url")


def collector_token(repo: Path) -> str | None:
    return os.environ.get("AI_ATTRIBUTION_COLLECTOR_TOKEN") or read_config(repo).get("collector_token")
