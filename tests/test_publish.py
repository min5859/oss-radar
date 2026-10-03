import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import publish


class PublishTests(unittest.TestCase):
    def test_dry_run_uses_configured_timezone_across_kst_midnight(self):
        for instant, expected_date in (
            (datetime(2026, 10, 3, 14, 59, tzinfo=timezone.utc), "2026-10-03"),
            (datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc), "2026-10-04"),
        ):
            with self.subTest(instant=instant), tempfile.TemporaryDirectory() as temp_dir:
                repos_file = Path(temp_dir) / "repos.json"
                repos_file.write_text(
                    '[{"full_name":"owner/repo","owner":"owner","name":"repo"}]'
                )
                def frozen_now(tz=None):
                    return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

                with patch.object(publish, "REPOS_FILE", repos_file), patch(
                    "publish.datetime"
                ) as clock, patch("publish.subprocess.run") as git, patch(
                    "publish.mark_published"
                ) as history, self.assertLogs(publish.log, level="INFO") as logs:
                    clock.now.side_effect = frozen_now
                    publish.main(["--dry-run"])
                self.assertIn(f"page={expected_date}-Weekly-OSS-Radar", logs.output[-1])
                git.assert_not_called()
                history.assert_not_called()

    def test_generation_header_is_actual_kst_time(self):
        instant = datetime(2026, 10, 3, 20, 0, tzinfo=timezone.utc)
        with patch("publish.datetime") as clock:
            clock.now.side_effect = lambda tz=None: (
                instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
            )
            content = publish.build_weekly_page([], "2026-10-04")
        self.assertIn("Auto-generated on 2026-10-04 05:00 KST", content)

    def test_git_push_still_pushes_when_commit_has_nothing_to_commit(self):
        nothing_to_commit = subprocess.CalledProcessError(
            1,
            ["git", "commit"],
            stderr="nothing to commit, working tree clean",
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "publish.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess(["git", "add"], 0),
                nothing_to_commit,
                subprocess.CompletedProcess(["git", "push"], 0),
            ],
        ) as run:
            publish.git_push(Path(temp_dir), "2026-09-25", {"PATH": "/usr/bin"})

        self.assertEqual(run.call_count, 3)
        self.assertEqual(run.call_args_list[-1].args[0][-1], "push")

    def test_git_push_does_not_swallow_push_failure(self):
        push_failure = subprocess.CalledProcessError(
            1,
            ["git", "push"],
            stderr="permission denied",
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "publish.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess(["git", "add"], 0),
                subprocess.CompletedProcess(["git", "commit"], 0),
                push_failure,
            ],
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                publish.git_push(Path(temp_dir), "2026-09-25", {"PATH": "/usr/bin"})


if __name__ == "__main__":
    unittest.main()
