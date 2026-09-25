import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from history import load_history, mark_published, published_repo_names, save_history


class HistoryTests(unittest.TestCase):
    def test_mark_published_adds_only_successful_publication_batch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "history.json"
            save_history(path, {"old/repo"})

            count = mark_published(
                path,
                [{"full_name": "new/repo"}, {"full_name": "old/repo"}],
            )

            self.assertEqual(count, 2)
            self.assertEqual(load_history(path), {"old/repo", "new/repo"})
            self.assertEqual(json.loads(path.read_text()), ["new/repo", "old/repo"])

    def test_published_repo_names_reads_generated_pages_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki_dir = Path(temp_dir)
            (wiki_dir / "2026-09-25-Weekly-OSS-Radar.md").write_text(
                "# Report\n\n## 1. [owner/one](https://github.com/owner/one)\n"
                "## 2. [owner/two](https://github.com/owner/two)\n",
                encoding="utf-8",
            )
            (wiki_dir / "Home.md").write_text(
                "## 1. [ignored/repo](https://github.com/ignored/repo)\n",
                encoding="utf-8",
            )

            self.assertEqual(
                published_repo_names(wiki_dir),
                {"owner/one", "owner/two"},
            )

    def test_load_history_rejects_non_string_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "history.json"
            path.write_text('["valid/repo", 3]', encoding="utf-8")

            with self.assertRaises(ValueError):
                load_history(path)


if __name__ == "__main__":
    unittest.main()
