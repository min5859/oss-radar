#!/usr/bin/env python3
"""Discover trending GitHub repos via Search API and Trending page."""

import json
import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).resolve().parent.parent / "logs" / "discover.log"),
    ],
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
HISTORY_FILE = ROOT / "data" / "history.json"
OUTPUT_FILE = ROOT / "data" / "repos.json"

GITHUB_API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

import os
if token := os.environ.get("GITHUB_TOKEN"):
    HEADERS["Authorization"] = f"Bearer {token}"


def load_history() -> set[str]:
    if HISTORY_FILE.exists():
        return set(json.loads(HISTORY_FILE.read_text()))
    return set()


def save_history(history: set[str]) -> None:
    HISTORY_FILE.write_text(json.dumps(sorted(history), indent=2))


def fetch_github_search(lookback_days: int, min_stars: int, categories: list[str]) -> list[dict]:
    """GitHub Search API로 최근 N일 star 급상승 레포 수집."""
    since = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    if categories:
        topic_q = " ".join(f"topic:{c}" for c in categories)
        q = f"stars:>={min_stars} pushed:>={since} ({topic_q})"
    else:
        q = f"stars:>={min_stars} pushed:>={since}"

    repos = []
    page = 1
    while page <= 3:
        try:
            resp = requests.get(
                f"{GITHUB_API}/search/repositories",
                headers=HEADERS,
                params={"q": q, "sort": "stars", "order": "desc", "per_page": 50, "page": page},
                timeout=15,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items:
                break
            for item in items:
                repos.append({
                    "full_name": item["full_name"],
                    "owner": item["owner"]["login"],
                    "name": item["name"],
                    "description": item.get("description", "") or "",
                    "stars": item["stargazers_count"],
                    "forks": item["forks_count"],
                    "language": item.get("language", "") or "",
                    "topics": item.get("topics", []),
                    "url": item["html_url"],
                    "pushed_at": item.get("pushed_at", ""),
                    "created_at": item.get("created_at", ""),
                    "source": "github_search",
                })
            page += 1
            time.sleep(1)
        except requests.RequestException as e:
            log.warning("GitHub Search API failed (page %d): %s", page, e)
            break

    return repos


def fetch_github_trending() -> list[dict]:
    """github.com/trending 스크래핑으로 트렌딩 레포 수집."""
    repos = []
    try:
        resp = requests.get(
            "https://github.com/trending",
            headers={"User-Agent": "oss-radar/1.0"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for article in soup.select("article.Box-row"):
            h2 = article.select_one("h2 a")
            if not h2:
                continue
            path = h2["href"].strip("/")
            parts = path.split("/")
            if len(parts) != 2:
                continue
            owner, name = parts[0], parts[1]

            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            star_el = article.select_one("a[href$='/stargazers']")
            stars_text = star_el.get_text(strip=True).replace(",", "") if star_el else "0"
            try:
                stars = int(stars_text.replace("k", "000").replace(".", ""))
            except ValueError:
                stars = 0

            lang_el = article.select_one("[itemprop='programmingLanguage']")
            language = lang_el.get_text(strip=True) if lang_el else ""

            repos.append({
                "full_name": f"{owner}/{name}",
                "owner": owner,
                "name": name,
                "description": description,
                "stars": stars,
                "forks": 0,
                "language": language,
                "topics": [],
                "url": f"https://github.com/{owner}/{name}",
                "pushed_at": "",
                "created_at": "",
                "source": "github_trending",
            })
    except Exception as e:
        log.warning("GitHub Trending scraping failed: %s", e)

    return repos


def score_and_select(
    search_repos: list[dict],
    trending_repos: list[dict],
    count: int,
    history: set[str],
) -> list[dict]:
    """두 소스 합산 후 스코어링, 상위 N개 반환.

    score = star_velocity*0.5 + star_total_norm*0.3 + fork_norm*0.2
    trending 보너스: github_trending에 있으면 +0.1
    """
    search_weight = CONFIG["sources"]["github_search"]["weight"]
    trending_weight = CONFIG["sources"]["github_trending"]["weight"]

    trending_names = {r["full_name"] for r in trending_repos}

    # 전체 레포 병합 (full_name 기준 중복 제거, search 우선)
    merged: dict[str, dict] = {}
    for r in search_repos:
        merged[r["full_name"]] = r
    for r in trending_repos:
        if r["full_name"] not in merged:
            merged[r["full_name"]] = r

    candidates = [r for r in merged.values() if r["full_name"] not in history]
    if not candidates:
        return []

    max_stars = max((r["stars"] for r in candidates), default=1) or 1
    max_forks = max((r["forks"] for r in candidates), default=1) or 1

    # star_velocity: search 소스는 가중치 높게, trending만 있으면 낮게
    for r in candidates:
        star_total_norm = r["stars"] / max_stars
        fork_norm = r["forks"] / max_forks

        if r["source"] == "github_search":
            star_velocity = (r["stars"] / max_stars) * search_weight
        else:
            star_velocity = (r["stars"] / max_stars) * trending_weight

        base = star_velocity * 0.5 + star_total_norm * 0.3 + fork_norm * 0.2
        bonus = 0.1 if r["full_name"] in trending_names else 0.0
        r["score"] = round(base + bonus, 4)

    ranked = sorted(candidates, key=lambda x: x["score"], reverse=True)
    return ranked[:count]


def main() -> None:
    cfg_repos = CONFIG["repos"]
    count = cfg_repos["count"]
    lookback = cfg_repos["lookback_days"]
    min_stars = cfg_repos["min_stars"]
    categories = CONFIG.get("categories", [])
    history = load_history()

    log.info("Discovering repos (lookback=%d days, count=%d, min_stars=%d)", lookback, count, min_stars)

    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "logs").mkdir(exist_ok=True)

    search_repos: list[dict] = []
    if CONFIG["sources"]["github_search"]["enabled"]:
        search_repos = fetch_github_search(lookback, min_stars, categories)
        log.info("GitHub Search: %d repos found", len(search_repos))

    trending_repos: list[dict] = []
    if CONFIG["sources"]["github_trending"]["enabled"]:
        trending_repos = fetch_github_trending()
        log.info("GitHub Trending: %d repos found", len(trending_repos))

    if not search_repos and not trending_repos:
        log.error("No repos found from any source")
        sys.exit(1)

    selected = score_and_select(search_repos, trending_repos, count, history)
    if not selected:
        log.error("No new repos to analyze (all in history or none found)")
        sys.exit(1)

    log.info("Selected %d repos:", len(selected))
    for r in selected:
        log.info("  [%.4f] %s — %s", r["score"], r["full_name"], r["description"][:60])

    OUTPUT_FILE.write_text(json.dumps(selected, indent=2, ensure_ascii=False))
    log.info("Saved to %s", OUTPUT_FILE)

    for r in selected:
        history.add(r["full_name"])
    save_history(history)


if __name__ == "__main__":
    main()
