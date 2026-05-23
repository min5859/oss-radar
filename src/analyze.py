#!/usr/bin/env python3
"""Analyze GitHub repos using AI CLI (Claude / Codex / Cursor)."""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(ROOT / "logs" / "analyze.log"),
    ],
)
log = logging.getLogger(__name__)

CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
ANALYSIS_CFG = CONFIG["analysis"]

# Backward compat: old flat config without "provider" key or nested structure
if "provider" not in ANALYSIS_CFG:
    ANALYSIS_CFG["provider"] = "claude"
if isinstance(ANALYSIS_CFG.get("claude"), dict) is False:
    ANALYSIS_CFG["claude"] = {"model": ANALYSIS_CFG.get("claude_model", ANALYSIS_CFG.get("model", "sonnet"))}
    ANALYSIS_CFG["cursor"] = {"model": ANALYSIS_CFG.get("cursor_model", "sonnet-4")}

REPOS_FILE = ROOT / "data" / "repos.json"
ANALYSIS_DIR = ROOT / "data" / "analysis"
PROMPT_FILE = ROOT / ANALYSIS_CFG.get("prompt_file", "prompts/analyze.md")


def has_korean(text: str, min_chars: int = 10) -> bool:
    return len(re.findall(r"[가-힣]", text)) >= min_chars


def strip_bkit_footer(text: str) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "bkit Feature Usage" in line and line.startswith("─"):
            return "\n".join(lines[:i]).rstrip()
    return text


# ---------------------------------------------------------------------------
# Provider functions: (prompt, model) -> output text | None
# ---------------------------------------------------------------------------

def run_claude(prompt: str, model: str) -> str | None:
    cfg = ANALYSIS_CFG.get("claude", {})
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    api_key = cfg.get("api_key", "")
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    r = subprocess.run(
        ["claude", "-p", prompt, "--model", model, "--output-format", "text"],
        capture_output=True, text=True, env=env,
    )
    if r.returncode != 0:
        log.error("claude error: %s", r.stderr.strip()[:200])
        return None
    return strip_bkit_footer(r.stdout)


def run_codex(prompt: str, model: str) -> str | None:
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".md", delete=False)
    tmp.close()
    try:
        cmd = ["codex", "exec", "-", "-o", tmp.name, "--ephemeral"]
        if model:
            cmd += ["-m", model]
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True)
        if r.returncode != 0:
            log.error("codex error: %s", r.stderr.strip()[:200])
            return None
        output = Path(tmp.name).read_text()
        return output if output.strip() else None
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def run_cursor(prompt: str, model: str) -> str | None:
    cfg = ANALYSIS_CFG.get("cursor", {})
    env = dict(os.environ)
    api_key = cfg.get("api_key", "")
    if api_key:
        env["CURSOR_API_KEY"] = api_key
    r = subprocess.run(
        ["agent", "-p", "--model", model, "--output-format", "text", "--trust", prompt],
        capture_output=True, text=True, env=env,
    )
    if r.returncode != 0:
        log.error("cursor error: %s", r.stderr.strip()[:200])
        return None
    return r.stdout


PROVIDERS = {"claude": run_claude, "codex": run_codex, "cursor": run_cursor}


def check_provider(name: str) -> None:
    cmd = "agent" if name == "cursor" else name
    if not shutil.which(cmd):
        log.error("%s CLI not found in PATH", cmd)
        sys.exit(1)
    if name == "claude":
        cfg = ANALYSIS_CFG.get("claude", {})
        model = cfg.get("model", "sonnet")
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        api_key = cfg.get("api_key", "")
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        log.info("Checking claude CLI authentication (model: %s)...", model)
        r = subprocess.run(
            ["claude", "-p", "Reply with only: OK", "--model", model, "--output-format", "text"],
            capture_output=True, text=True, env=env,
        )
        if r.returncode != 0:
            log.error("claude CLI auth failed. Set api_key in config.yaml or run 'claude login'.")
            sys.exit(1)
        log.info("claude CLI authentication verified")
    else:
        log.info("%s CLI found: %s", name, shutil.which(cmd))


def main() -> None:
    provider_name = ANALYSIS_CFG["provider"]
    if provider_name not in PROVIDERS:
        log.error("Unknown provider: %s (available: %s)", provider_name, ", ".join(PROVIDERS))
        sys.exit(1)

    provider_cfg = ANALYSIS_CFG.get(provider_name, {})
    model = provider_cfg.get("model", "")
    max_retries = ANALYSIS_CFG.get("max_retries", 2)
    run_fn = PROVIDERS[provider_name]

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    if not REPOS_FILE.exists():
        log.error("repos.json not found. Run discover.py and fetch.py first.")
        sys.exit(1)

    check_provider(provider_name)
    prompt_template = PROMPT_FILE.read_text()
    repos = json.loads(REPOS_FILE.read_text())
    success = 0

    for repo in repos:
        full_name = repo["full_name"]
        owner = repo["owner"]
        name = repo["name"]
        safe_name = f"{owner}_{name}"
        output_file = ANALYSIS_DIR / f"{safe_name}.md"

        if output_file.exists() and output_file.stat().st_size > 0:
            log.info("Analysis already exists: %s", output_file)
            success += 1
            continue

        readme = repo.get("readme", "")
        if not readme:
            log.error("No README for %s, skipping", full_name)
            continue

        log.info("Analyzing: %s (%s stars) [provider=%s, model=%s]",
                 full_name, repo.get("stars", 0), provider_name, model or "default")

        prompt = (
            f"{prompt_template}\n\n---\n\n"
            f"## 레포지토리 정보\n"
            f"- **이름**: {full_name}\n"
            f"- **URL**: https://github.com/{full_name}\n"
            f"- **설명**: {repo.get('description', '')}\n"
            f"- **Stars**: {repo.get('stars', 0)}\n"
            f"- **언어**: {repo.get('language', '')}\n"
            f"- **토픽**: {', '.join(repo.get('topics', []))}\n"
            f"- **라이선스**: {repo.get('license', '')}\n\n"
            f"## README\n\n{readme}"
        )

        analysis_ok = False
        for attempt in range(1, max_retries + 2):
            if attempt > 1:
                log.info("Retry %d/%d for %s (not in Korean)", attempt - 1, max_retries, full_name)
                time.sleep(3)

            result = run_fn(prompt, model)
            if result and has_korean(result):
                output_file.write_text(result)
                analysis_ok = True
                log.info("Analysis saved: %s (%d bytes)", output_file, len(result.encode()))
                break
            elif result:
                log.error("Attempt %d: output for %s is not in Korean", attempt, full_name)
            else:
                log.error("Attempt %d: CLI error for %s", attempt, full_name)

        if analysis_ok:
            success += 1
        else:
            log.error("All retries exhausted for %s", full_name)

        time.sleep(2)

    if success == 0:
        log.error("No repos were successfully analyzed")
        sys.exit(1)

    log.info("Analysis complete (%d/%d repos)", success, len(repos))


if __name__ == "__main__":
    main()
