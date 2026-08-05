import unittest
from unittest.mock import patch, MagicMock
import sys
import json
import os

# Add parent directory to path so run_antigravity can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import run_antigravity


class TestRunAntigravity(unittest.TestCase):
    def test_parse_args_defaults(self):
        args = run_antigravity.parse_args([])
        self.assertEqual(args.mode, "code-review")
        self.assertEqual(args.model, "")
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

    @patch("subprocess.run")
    def test_get_pr_diff_error(self, mock_run):
        mock_run.side_effect = Exception("gh command failed")
        with self.assertRaises(RuntimeError):
            run_antigravity.get_pr_diff(10)

    @patch("subprocess.run")
    def test_get_pr_metadata_error(self, mock_run):
        mock_run.side_effect = Exception("gh command failed")
        with self.assertRaises(RuntimeError):
            run_antigravity.get_pr_metadata(10)

    @patch("asyncio.sleep")
    def test_run_antigravity_agent_retry_on_429(self, mock_sleep):
        class MockAgent:
            def __init__(self, config):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def chat(self, prompt):
                raise Exception("Quota exceeded for quota metric (429)")

        with patch.object(run_antigravity, "Agent", MockAgent), \
             patch.object(run_antigravity, "CapabilitiesConfig", MagicMock()), \
             patch.object(run_antigravity, "LocalAgentConfig", MagicMock()):
            with self.assertRaises(Exception) as ctx:
                import asyncio
                asyncio.run(run_antigravity.run_antigravity_agent("prompt", "sys"))
            self.assertIn("Quota exceeded", str(ctx.exception))
            self.assertEqual(mock_sleep.call_count, 2)

    @patch("asyncio.sleep")
    def test_run_antigravity_agent_retry_success_on_second_attempt(self, mock_sleep):
        attempt_counter = 0

        class MockAgent:
            def __init__(self, config):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def chat(self, prompt):
                nonlocal attempt_counter
                attempt_counter += 1
                if attempt_counter == 1:
                    raise Exception("RESOURCE_EXHAUSTED: Rate limit exceeded (429)")

                async def mock_gen():
                    yield "Success response"

                return mock_gen()

        with patch.object(run_antigravity, "Agent", MockAgent), \
             patch.object(run_antigravity, "CapabilitiesConfig", MagicMock()), \
             patch.object(run_antigravity, "LocalAgentConfig", MagicMock()):
            import asyncio
            result = asyncio.run(run_antigravity.run_antigravity_agent("prompt", "sys"))
            self.assertEqual(result, "Success response")
            self.assertEqual(mock_sleep.call_count, 1)

    @patch("asyncio.sleep")
    def test_run_antigravity_agent_non_retryable_error_fails_immediately(self, mock_sleep):
        class MockAgent:
            def __init__(self, config):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def chat(self, prompt):
                raise ValueError("Invalid configuration or unauthorized (401)")

        with patch.object(run_antigravity, "Agent", MockAgent), \
             patch.object(run_antigravity, "CapabilitiesConfig", MagicMock()), \
             patch.object(run_antigravity, "LocalAgentConfig", MagicMock()):
            import asyncio
            with self.assertRaises(ValueError):
                asyncio.run(run_antigravity.run_antigravity_agent("prompt", "sys"))
            self.assertEqual(mock_sleep.call_count, 0)

    def test_extract_inline_comments(self):
        sample_report = (
            "### Overview\nGreat changes.\n\n"
            "#### 1. 🚨 Critical Issue\n"
            "**Location:** [src/main.py:L42-L45]\n\n"
            "This logic contains a bug.\n\n"
            "#### 2. ⚠️ Minor Readability\n"
            "**Location:** [utils/helper.py:L10]\n\n"
            "Consider simplifying this helper."
        )
        comments = run_antigravity.extract_inline_comments(sample_report)
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["path"], "src/main.py")
        self.assertEqual(comments[0]["start_line"], 42)
        self.assertEqual(comments[0]["line"], 45)
        self.assertEqual(comments[0]["start_side"], "RIGHT")
        self.assertEqual(comments[1]["path"], "utils/helper.py")
        self.assertEqual(comments[1]["line"], 10)
        self.assertNotIn("start_line", comments[1])

    @patch.dict("os.environ", {"GITHUB_REPOSITORY": "owner/repo"})
    @patch("subprocess.run")
    def test_post_github_comment_inline_review_success(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"number": 10, "headRefOid": "abc1234"})),
            MagicMock(returncode=0, stdout="{}"),
        ]
        report = "#### 1. Bug\n**Location:** [main.py:L10]\nFix this."
        run_antigravity.post_github_comment(10, report, "code-review")
        self.assertEqual(mock_run.call_count, 2)

    @patch.dict("os.environ", {"GITHUB_REPOSITORY": "owner/repo"})
    @patch("subprocess.run")
    def test_post_github_comment_inline_review_fallback_on_api_error(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"number": 10, "headRefOid": "abc1234"})),
            MagicMock(returncode=1, stderr="HTTP 422: Line number must be part of the diff"),
            MagicMock(returncode=0, stdout="{}"),
        ]
        report = "#### 1. Bug\n**Location:** [main.py:L999]\nFix this."
        run_antigravity.post_github_comment(10, report, "code-review")
        self.assertEqual(mock_run.call_count, 3)

    def test_extract_inline_comments_with_bullet_list_and_inverted_range(self):
        sample_report = (
            "#### 1. Bug\n"
            "**Location:** [src/main.py:L50-L40]\n"
            "This logic fails because:\n"
            "- First reason\n"
            "- Second reason\n"
        )
        comments = run_antigravity.extract_inline_comments(sample_report)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["start_line"], 40)
        self.assertEqual(comments[0]["line"], 50)
        self.assertIn("- First reason", comments[0]["body"])
        self.assertIn("- Second reason", comments[0]["body"])

    def test_extract_inline_comments_with_code_block_comments(self):
        sample_report = (
            "#### 1. Bug Fix\n"
            "**Location:** [src/main.py:L10]\n"
            "Consider updating the code:\n"
            "```python\n"
            "# Fix bug here\n"
            "return True\n"
            "```\n\n"
            "#### 2. Readability\n"
            "**Location**: [src/utils.py:L20]\n"
            "Simplify this function."
        )
        comments = run_antigravity.extract_inline_comments(sample_report)
        self.assertEqual(len(comments), 2)
        self.assertIn("# Fix bug here", comments[0]["body"])
        self.assertEqual(comments[1]["path"], "src/utils.py")

    def test_extract_inline_comments_dot_directory_and_trailing_summary(self):
        sample_report = (
            "#### 1. Security Risk\n"
            "**Location:** [./.github/workflows/review.yml:L12]\n"
            "Missing permission restrictions.\n\n"
            "### Summary Recommendations\n"
            "Ensure all workflows adhere to least-privilege principles."
        )
        comments = run_antigravity.extract_inline_comments(sample_report)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["path"], ".github/workflows/review.yml")
        self.assertNotIn("Summary Recommendations", comments[0]["body"])

    def test_extract_inline_comments_with_code_block_before_trailing_summary(self):
        sample_report = (
            "#### 1. Security Risk\n"
            "**Location:** [./.github/workflows/review.yml:L12]\n"
            "Missing permissions:\n"
            "```yaml\n"
            "permissions: read-all\n"
            "```\n"
            "Fix this permission setting.\n\n"
            "### Summary Recommendations\n"
            "Ensure all workflows adhere to least privilege."
        )
        comments = run_antigravity.extract_inline_comments(sample_report)
        self.assertEqual(len(comments), 1)
        self.assertIn("permissions: read-all", comments[0]["body"])
        self.assertIn("Fix this permission setting.", comments[0]["body"])
        self.assertNotIn("Summary Recommendations", comments[0]["body"])

    def test_extract_inline_comments_ignores_location_in_fenced_code_block(self):
        sample_report = (
            "#### 1. Real Finding\n"
            "**Location:** [src/main.py:L15]\n"
            "Check out this sample format:\n"
            "```markdown\n"
            "**Location:** [example.py:L999]\n"
            "```\n"
            "End of report."
        )
        comments = run_antigravity.extract_inline_comments(sample_report)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["path"], "src/main.py")
        self.assertIn("example.py:L999", comments[0]["body"])

    def test_extract_inline_comments_backtick_path_and_empty_body(self):
        sample_report = (
            "#### 1. Backtick Path\n"
            "**Location:** [`src/utils.py`:L20]\n"
            "Fix this function.\n\n"
            "#### 2. Empty Body\n"
            "**Location:** [src/empty.py:L10]\n"
        )
        comments = run_antigravity.extract_inline_comments(sample_report)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["path"], "src/utils.py")

    def test_extract_inline_comments_recommendation_subheader_kept(self):
        """Bare '### Recommendation' inside a finding should NOT truncate the body."""
        sample_report = (
            "#### 1. Performance Issue\n"
            "**Location:** [src/main.py:L30]\n"
            "This function is slow.\n\n"
            "### Recommendation\n"
            "Use caching to speed it up.\n"
        )
        comments = run_antigravity.extract_inline_comments(sample_report)
        self.assertEqual(len(comments), 1)
        self.assertIn("### Recommendation", comments[0]["body"])
        self.assertIn("Use caching to speed it up.", comments[0]["body"])

    def test_extract_inline_comments_single_newline_summary_truncated(self):
        """Single-newline before '### Summary' should still be truncated."""
        sample_report = (
            "#### 1. Bug\n"
            "**Location:** [src/main.py:L10]\n"
            "Fix this bug.\n"
            "### Summary\n"
            "Overall this PR looks good."
        )
        comments = run_antigravity.extract_inline_comments(sample_report)
        self.assertEqual(len(comments), 1)
        self.assertNotIn("Overall this PR looks good.", comments[0]["body"])

    def test_extract_inline_comments_decoupled_header_and_leading_slash(self):
        """Verify header extraction works when introductory lines exist between heading and Location, and leading slashes are stripped."""
        sample_report = (
            "#### 1. Critical Bug\n"
            "Introductory details about the problem.\n"
            "**Location:** [/src/main.py:L10]\n"
            "Body of finding 1.\n\n"
            "#### 2. Minor Edge Case\n"
            "**Location:** [utils/helper.py:L20]\n"
            "Body of finding 2."
        )
        comments = run_antigravity.extract_inline_comments(sample_report)
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["path"], "src/main.py")
        self.assertIn("#### 1. Critical Bug", comments[0]["body"])
        self.assertIn("Body of finding 1.", comments[0]["body"])
        self.assertNotIn("#### 2. Minor Edge Case", comments[0]["body"])
        self.assertEqual(comments[1]["path"], "utils/helper.py")
        self.assertIn("#### 2. Minor Edge Case", comments[1]["body"])


    @patch("os.path.isfile")
    @patch("builtins.open", new_callable=MagicMock)
    def test_get_repo_instructions_and_build_full_prompt(self, mock_open, mock_isfile):
        mock_isfile.side_effect = lambda path: path in ("CLAUDE.md", "GEMINI.md")
        mock_file_handle = MagicMock()
        mock_file_handle.__enter__.return_value.read.return_value = "Always use strict typing."
        mock_open.return_value = mock_file_handle

        prompt = run_antigravity.build_full_prompt(
            mode="code-review",
            pr_meta={"title": "Fix bug", "number": 412},
            diff="diff --git a/a.py b/a.py",
            addendum="Extra advice",
        )
        self.assertIn("Repository Guidelines & Standards:", prompt)
        self.assertIn("--- From `CLAUDE.md` ---", prompt)
        self.assertIn("--- From `GEMINI.md` ---", prompt)
        self.assertIn("Always use strict typing.", prompt)
        self.assertIn("Extra advice", prompt)


if __name__ == "__main__":
    unittest.main()
