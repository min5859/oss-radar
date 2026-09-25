"""Helpers for managing the durable published-repository history."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Iterable


REPO_HEADING_RE = re.compile(r"^## \d+\. \[([^\]]+/[^\]]+)\]\(", re.MULTILINE)


def load_history(path: Path) -> set[str]:
    """Load repository full names from a history JSON file."""
    if not path.exists():
        return set()

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError(f"history must be a JSON string list: {path}")
    return set(data)


def save_history(path: Path, history: Iterable[str]) -> None:
    """Atomically persist repository full names in deterministic order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(sorted(set(history)), indent=2, ensure_ascii=False) + "\n"

    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_file.write(payload)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_name = temp_file.name
        os.replace(temp_name, path)
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def mark_published(path: Path, repos: Iterable[dict]) -> int:
    """Add successfully published repositories to history and return new count."""
    history = load_history(path)
    history.update(repo["full_name"] for repo in repos)
    save_history(path, history)
    return len(history)


def published_repo_names(wiki_dir: Path) -> set[str]:
    """Extract published repository full names from generated Wiki pages."""
    published: set[str] = set()
    for page in wiki_dir.glob("*-Weekly-OSS-Radar.md"):
        published.update(REPO_HEADING_RE.findall(page.read_text(encoding="utf-8")))
    return published
