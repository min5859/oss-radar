#!/usr/bin/env python3
"""Publish OSS Radar analysis results to GitHub Wiki."""

import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).resolve().parent.parent / "logs" / "publish.log"),
    ],
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
REPOS_FILE = ROOT / "data" / "repos.json"
ANALYSIS_DIR = ROOT / "data" / "analysis"


def build_weekly_page(repos: list[dict], date_str: str) -> str:
    """주간 OSS Radar 위키 페이지 빌드."""
    lines = [
        f"# Weekly OSS Radar - {date_str}",
        "",
        f"> Auto-generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} KST",
        "",
        "---",
        "",
    ]

    for i, repo in enumerate(repos, 1):
        full_name = repo["full_name"]
        owner = repo["owner"]
        name = repo["name"]
        description = repo.get("description", "")
        stars = repo.get("stars", 0)
        language = repo.get("language", "")
        topics = repo.get("topics", [])
        license_ = repo.get("license", "")
        url = repo.get("url", f"https://github.com/{full_name}")
        analysis_path = ANALYSIS_DIR / f"{owner}_{name}.md"

        lines.append(f"## {i}. [{full_name}]({url})")
        lines.append("")
        if description:
            lines.append(f"> {description}")
            lines.append("")
        lines.append(f"- **Stars**: {stars:,}")
        if language:
            lines.append(f"- **Language**: {language}")
        if topics:
            lines.append(f"- **Topics**: {', '.join(topics)}")
        if license_:
            lines.append(f"- **License**: {license_}")
        lines.append("")

        if analysis_path.exists():
            analysis = analysis_path.read_text(encoding="utf-8").strip()
            lines.append(analysis)
        else:
            lines.append(f"> *분석 생성에 실패하여 레포 설명을 표시합니다.*")
            if description:
                lines.append(f"\n{description}")

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def update_home(wiki_dir: Path, page_name: str, date_str: str) -> None:
    """Home.md에 새 주간 페이지 링크 추가."""
    home = wiki_dir / "Home.md"

    if home.exists():
        content = home.read_text(encoding="utf-8")
    else:
        content = "# OSS Radar\n\n주목할 오픈소스 프로젝트 주간 리뷰 아카이브\n\n## Weekly Reports\n\n"

    entry = f"- [{date_str} Weekly OSS Radar]({page_name})"

    if entry in content:
        log.info("Home.md already contains entry for %s", date_str)
        return

    marker = "## Weekly Reports"
    if marker in content:
        idx = content.index(marker) + len(marker)
        content = content[:idx] + f"\n\n{entry}" + content[idx:]
    else:
        content += f"\n## Weekly Reports\n\n{entry}\n"

    home.write_text(content, encoding="utf-8")
    log.info("Updated Home.md")


def git_push(wiki_dir: Path, date_str: str) -> None:
    """변경 사항을 wiki 레포에 커밋 및 푸시."""
    cmds = [
        ["git", "-C", str(wiki_dir), "add", "-A"],
        ["git", "-C", str(wiki_dir), "commit", "-m", f"Weekly OSS Radar - {date_str}"],
        ["git", "-C", str(wiki_dir), "push"],
    ]
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            if "nothing to commit" in (e.stdout or "") + (e.stderr or ""):
                log.info("Nothing to commit")
                return
            log.error("Git command failed: %s\n%s", " ".join(cmd), e.stderr)
            raise


def main() -> None:
    if not REPOS_FILE.exists():
        log.error("repos.json not found. Run discover.py and fetch.py first.")
        sys.exit(1)

    repos = json.loads(REPOS_FILE.read_text())
    if not repos:
        log.error("repos.json is empty.")
        sys.exit(1)

    repo_cfg = CONFIG["wiki"]["repo"]
    wiki_url = f"git@github.com:{repo_cfg}.wiki.git"
    date_str = datetime.now().strftime("%Y-%m-%d")
    page_name = f"{date_str}-Weekly-OSS-Radar"

    wiki_dir = ROOT / "data" / "wiki_clone"
    if wiki_dir.exists():
        log.info("Pulling existing wiki clone")
        try:
            subprocess.run(
                ["git", "-C", str(wiki_dir), "pull", "--rebase"],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError:
            log.warning("Pull failed, removing stale clone and re-cloning")
            shutil.rmtree(wiki_dir)

    if not wiki_dir.exists():
        log.info("Cloning wiki repo: %s", wiki_url)
        try:
            subprocess.run(
                ["git", "clone", wiki_url, str(wiki_dir)],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError:
            log.warning("Clone failed (wiki may be empty), initializing")
            wiki_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=str(wiki_dir), check=True, capture_output=True)
            subprocess.run(
                ["git", "remote", "add", "origin", wiki_url],
                cwd=str(wiki_dir), check=True, capture_output=True,
            )

    page_content = build_weekly_page(repos, date_str)
    page_file = wiki_dir / f"{page_name}.md"
    page_file.write_text(page_content, encoding="utf-8")
    log.info("Created %s", page_file)

    update_home(wiki_dir, page_name, date_str)
    git_push(wiki_dir, date_str)
    log.info("Published to wiki: %s", page_name)


if __name__ == "__main__":
    main()
