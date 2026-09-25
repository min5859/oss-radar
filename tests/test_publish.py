import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import publish


class PublishTests(unittest.TestCase):
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
