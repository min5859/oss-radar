#!/usr/bin/env python3
"""Verify GitHub Wiki push authentication without changing the remote."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from publish import git_env  # noqa: E402


def run(command: list[str], env: dict[str, str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"Git credential check failed: {detail}")


def main() -> None:
    token = os.environ.get("GITHUB_WIKI_TOKEN", "")
    if not token:
        raise SystemExit("GITHUB_WIKI_TOKEN is not set")

    repo = os.environ.get("OSS_RADAR_WIKI_URL", "")
    if not repo:
        raise SystemExit("OSS_RADAR_WIKI_URL is not set")
    if "@" in repo.split("://", 1)[-1].split("/", 1)[0]:
        raise SystemExit("refusing a Wiki URL containing embedded credentials")

    env = git_env()
    with tempfile.TemporaryDirectory(prefix="oss-radar-wiki-check-") as temp_dir:
        checkout = Path(temp_dir) / "wiki"
        run(["git", "clone", "--depth", "1", repo, str(checkout)], env)
        run(
            [
                "git",
                "-C",
                str(checkout),
                "push",
                "--dry-run",
                "origin",
                "HEAD:refs/heads/master",
            ],
            env,
        )

    print("Wiki credential check passed; no remote changes were made")


if __name__ == "__main__":
    main()
