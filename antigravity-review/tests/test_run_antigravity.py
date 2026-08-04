import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path so run_antigravity can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import run_antigravity


class TestRunAntigravity(unittest.TestCase):
    def test_parse_args_defaults(self):
        args = run_antigravity.parse_args([])
        self.assertEqual(args.mode, "code-review")
        self.assertEqual(args.model, "gemini-2.5-flash")
        self.assertEqual(args.prompt_addendum, "")
        self.assertEqual(args.trigger_policy, "any")
        self.assertFalse(args.post_comment)
        self.assertFalse(args.dry_run)

    def test_parse_args_trigger_policy(self):
        args_on_push = run_antigravity.parse_args(["--trigger-policy", "on-push"])
        self.assertEqual(args_on_push.trigger_policy, "on-push")

        args_on_request = run_antigravity.parse_args(["--trigger-policy", "on-request"])
        self.assertEqual(args_on_request.trigger_policy, "on-request")

    def test_parse_args_custom(self):
        args = run_antigravity.parse_args([
            "--mode", "security-audit",
            "--pr-number", "42",
            "--model", "gemini-2.5-pro",
            "--prompt-addendum", "Focus on SQL injection",
            "--post-comment",
            "--dry-run"
        ])
        self.assertEqual(args.mode, "security-audit")
        self.assertEqual(args.pr_number, 42)
        self.assertEqual(args.model, "gemini-2.5-pro")
        self.assertEqual(args.prompt_addendum, "Focus on SQL injection")
        self.assertTrue(args.post_comment)
        self.assertTrue(args.dry_run)

    def test_build_full_prompt(self):
        pr_meta = {
            "number": 10,
            "title": "Add feature X",
            "body": "This PR adds feature X for better throughput."
        }
        diff = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new"
        addendum = "Pay close attention to concurrency."

        prompt = run_antigravity.build_full_prompt("code-review", pr_meta, diff, addendum)
        self.assertIn("Task Mode: CODE-REVIEW", prompt)
        self.assertIn("Pull Request: #10 - Add feature X", prompt)
        self.assertIn("This PR adds feature X", prompt)
        self.assertIn("Pay close attention to concurrency.", prompt)
        self.assertIn("+++ b/file.py", prompt)

    def test_build_full_prompt_security_audit(self):
        pr_meta = {"number": 15, "title": "Update auth logic", "body": "Refactor tokens"}
        diff = "+ token = 'secret'"
        prompt = run_antigravity.build_full_prompt("security-audit", pr_meta, diff, "")
        self.assertIn("Task Mode: SECURITY-AUDIT", prompt)
        self.assertIn("OWASP Top 10 vulnerabilities", prompt)


if __name__ == "__main__":
    unittest.main()
