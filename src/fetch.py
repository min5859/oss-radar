#!/usr/bin/env python3
"""Fetch README and metadata for each repo in data/repos.json."""

import base64
import json
import logging
import sys
import time
from pathlib import Path

import requests
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).resolve().parent.parent / "logs" / "fetch.log"),
    ],
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
REPOS_FILE = ROOT / "data" / "repos.json"

GITHUB_API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
README_MAX_CHARS = 40_000

import os
if token := os.environ.get("GITHUB_TOKEN"):
    HEADERS["Authorization"] = f"Bearer {token}"


def fetch_repo_meta(owner: str, name: str) -> dict:
    """GitHub API /repos/{owner}/{repo} — 기본 메타데이터."""
    try:
        resp = requests.get(f"{GITHUB_API}/repos/{owner}/{name}", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return {
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "language": data.get("language", "") or "",
            "topics": data.get("topics", []),
            "license": (data.get("license") or {}).get("spdx_id", "") or "",
            "open_issues": data.get("open_issues_count", 0),
            "watchers": data.get("watchers_count", 0),
            "description": data.get("description", "") or "",
            "homepage": data.get("homepage", "") or "",
            "archived": data.get("archived", False),
        }
    except requests.RequestException as e:
        log.warning("Metadata fetch failed for %s/%s: %s", owner, name, e)
        return {}


def fetch_readme(owner: str, name: str) -> str:
    """GitHub API /repos/{owner}/{repo}/readme — README 원문."""
    try:
        resp = requests.get(
            f"{GITHUB_API}/repos/{owner}/{name}/readme",
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", "")
        encoding = data.get("encoding", "base64")
        if encoding == "base64":
            text = base64.b64decode(content).decode("utf-8", errors="replace")
        else:
            text = content
        if len(text) > README_MAX_CHARS:
            log.info("README truncated: %d → %d chars", len(text), README_MAX_CHARS)
            text = text[:README_MAX_CHARS]
        return text
    except requests.RequestException as e:
        log.warning("README fetch failed for %s/%s: %s", owner, name, e)
        return ""


def main() -> None:
    if not REPOS_FILE.exists():
        log.error("repos.json not found. Run discover.py first.")
        sys.exit(1)

    repos = json.loads(REPOS_FILE.read_text())
    if not repos:
        log.error("repos.json is empty.")
        sys.exit(1)

    success = 0
    for repo in repos:
        owner = repo["owner"]
        name = repo["name"]
        full_name = repo["full_name"]
        log.info("Fetching %s ...", full_name)

        meta = fetch_repo_meta(owner, name)
        repo.update(meta)
        time.sleep(1)

        readme = fetch_readme(owner, name)
        repo["readme"] = readme
        time.sleep(1)

        if readme:
            success += 1
            log.info("  README: %d chars, stars: %d, lang: %s", len(readme), repo.get("stars", 0), repo.get("language", ""))
        else:
            log.warning("  No README for %s", full_name)

    REPOS_FILE.write_text(json.dumps(repos, indent=2, ensure_ascii=False))
    log.info("Fetched %d/%d repos → %s", success, len(repos), REPOS_FILE)

    if success == 0:
        log.error("No READMEs fetched")
        sys.exit(1)


if __name__ == "__main__":
    main()
