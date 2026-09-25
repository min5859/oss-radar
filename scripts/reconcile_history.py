#!/usr/bin/env python3
"""Reconcile history.json with repositories actually published to the Wiki."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from history import load_history, published_repo_names, save_history  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=ROOT / "data" / "history.json")
    parser.add_argument("--wiki-dir", type=Path, default=ROOT / "data" / "wiki_clone")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write reconciled history after creating a timestamped backup",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    current = load_history(args.history)
    published = published_repo_names(args.wiki_dir)
    unpublished = current - published
    missing = published - current

    print(f"history={len(current)}")
    print(f"published={len(published)}")
    print(f"history_not_published={len(unpublished)}")
    print(f"published_not_history={len(missing)}")

    if not args.apply:
        print("check-only: pass --apply to create a backup and reconcile history")
        return
    if not published:
        raise SystemExit("refusing to replace history: no published repositories found")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = args.history.with_name(f"{args.history.name}.backup-{timestamp}")
    if backup.exists():
        raise SystemExit(f"backup already exists: {backup}")
    shutil.copy2(args.history, backup)
    save_history(args.history, published)
    print(f"backup={backup}")
    print(f"reconciled={args.history}")


if __name__ == "__main__":
    main()
