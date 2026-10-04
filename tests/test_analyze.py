import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import analyze


class CursorInvocationTests(unittest.TestCase):
    def test_cursor_uses_ask_mode_and_configured_model(self):
        model = analyze.ANALYSIS_CFG["cursor"]["model"]
        self.assertEqual(model, "claude-sonnet-5-5-medium")
        completed = subprocess.CompletedProcess(["agent"], 0, stdout="분석 결과", stderr="")
        with patch("analyze.subprocess.run", return_value=completed) as run:
            result = analyze.run_cursor("프롬프트", model)

        command = run.call_args.args[0]
        self.assertEqual(result, "분석 결과")
        self.assertEqual(command[command.index("--mode") + 1], "ask")
        self.assertEqual(command[command.index("--model") + 1], model)
        self.assertIn("--trust", command)


if __name__ == "__main__":
    unittest.main()
