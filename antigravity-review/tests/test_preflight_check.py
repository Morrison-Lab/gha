#!/usr/bin/env python3
"""Unit tests for preflight_check.py."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
import preflight_check


class TestPreflightCheck(unittest.TestCase):
    def test_check_changelog_fragments_positive_and_negative(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            changelog_dir = os.path.join(tmp_dir, "changelog.d")
            os.makedirs(changelog_dir)

            # Valid fragment
            with open(os.path.join(changelog_dir, "valid.added.md"), "w", encoding="utf-8") as f:
                f.write("- Add feature X (#100).\n")

            # README.md should be ignored
            with open(os.path.join(changelog_dir, "README.md"), "w", encoding="utf-8") as f:
                f.write("# Changelog Fragments\n\nInstructions here.\n")

            # Patch repo_root in check_changelog_fragments
            orig_abspath = os.path.abspath
            with patch("glob.glob", return_value=[
                os.path.join(changelog_dir, "valid.added.md"),
                os.path.join(changelog_dir, "README.md")
            ]):
                self.assertTrue(preflight_check.check_changelog_fragments())

            # Invalid fragment missing bullet
            with open(os.path.join(changelog_dir, "invalid.added.md"), "w", encoding="utf-8") as f:
                f.write("Add feature Y without bullet (#101).\n")

            with patch("glob.glob", return_value=[
                os.path.join(changelog_dir, "invalid.added.md")
            ]):
                self.assertFalse(preflight_check.check_changelog_fragments())

    def test_extract_workflow_inputs(self):
        sample_workflow = (
            "name: Test Workflow\n"
            "on:\n"
            "  workflow_call:\n"
            "    inputs:\n"
            "      mode:\n"
            "        type: string\n"
            "      pr-number:\n"
            "        type: string\n"
        )
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            f.write(sample_workflow)
            f_path = f.name

        try:
            inputs = preflight_check.extract_workflow_inputs(f_path)
            self.assertEqual(inputs, ["mode", "pr-number"])
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_check_action_docs_sync_mock(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workflow_dir = os.path.join(tmp_dir, ".github", "workflows")
            doc_dir = os.path.join(tmp_dir, "website", "reference")
            website_dir = os.path.join(tmp_dir, "website")
            os.makedirs(workflow_dir)
            os.makedirs(doc_dir)

            wf_path = os.path.join(workflow_dir, "antigravity-code-review.yml")
            doc_path = os.path.join(doc_dir, "antigravity-code-review.qmd")
            readme_path = os.path.join(tmp_dir, "README.md")
            workflows_path = os.path.join(website_dir, "workflows.qmd")

            with open(wf_path, "w", encoding="utf-8") as f:
                f.write("on:\n  workflow_call:\n    inputs:\n      mode:\n        type: string\n")

            with open(doc_path, "w", encoding="utf-8") as f:
                f.write("| `mode` | string |\n")

            with open(readme_path, "w", encoding="utf-8") as f:
                f.write("| `antigravity-code-review.yml` | `mode` |\n")

            with open(workflows_path, "w", encoding="utf-8") as f:
                f.write("| `antigravity-code-review.yml` | `mode` |\n")

            with patch("os.path.abspath", return_value=tmp_dir):
                self.assertTrue(preflight_check.check_action_docs_sync())

            # Missing doc in reference qmd case
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write("| `other` | string |\n")

            with patch("os.path.abspath", return_value=tmp_dir):
                self.assertFalse(preflight_check.check_action_docs_sync())

            # Restore reference qmd, make README.md missing input
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write("| `mode` | string |\n")

            with open(readme_path, "w", encoding="utf-8") as f:
                f.write("| `antigravity-code-review.yml` | `other` |\n")

            with patch("os.path.abspath", return_value=tmp_dir):
                self.assertFalse(preflight_check.check_action_docs_sync())

            # Restore README.md, make website/workflows.qmd missing input
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write("| `antigravity-code-review.yml` | `mode` |\n")

            with open(workflows_path, "w", encoding="utf-8") as f:
                f.write("| `antigravity-code-review.yml` | `other` |\n")

            with patch("os.path.abspath", return_value=tmp_dir):
                self.assertFalse(preflight_check.check_action_docs_sync())

            # Row scoping test: input `mode` exists in a sibling row but not in antigravity-code-review.yml row
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write("| `claude.yml` | `mode` |\n| `antigravity-code-review.yml` | `other` |\n")

            with open(workflows_path, "w", encoding="utf-8") as f:
                f.write("| `antigravity-code-review.yml` | `mode` |\n")

            with patch("os.path.abspath", return_value=tmp_dir):
                self.assertFalse(preflight_check.check_action_docs_sync())

    def test_extract_workflow_inputs_ignores_secrets(self):
        """Regression: secrets block at same depth must not be captured as inputs."""
        sample_workflow = (
            "name: Test Workflow\n"
            "on:\n"
            "  workflow_call:\n"
            "    inputs:\n"
            "      mode:\n"
            "        type: string\n"
            "      pr-number:\n"
            "        type: string\n"
            "    secrets:\n"
            "      GEMINI_API_KEY:\n"
            "        required: true\n"
            "      SUBMODULES_TOKEN:\n"
            "        required: false\n"
        )
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".yml") as f:
            f.write(sample_workflow)
            f_path = f.name

        try:
            inputs = preflight_check.extract_workflow_inputs(f_path)
            self.assertEqual(inputs, ["mode", "pr-number"])
            self.assertNotIn("GEMINI_API_KEY", inputs)
            self.assertNotIn("SUBMODULES_TOKEN", inputs)
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_extract_workflow_inputs_handles_inline_comments_and_quotes(self):
        """Verify extract_workflow_inputs strips inline comments and quotes."""
        sample_workflow = (
            "on:\n"
            "  workflow_call:\n"
            "    inputs: # inline comment\n"
            "      'mode': # operational mode\n"
            "        type: string\n"
            "      \"pr-number\":\n"
            "        type: string\n"
        )
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".yml") as f:
            f.write(sample_workflow)
            f_path = f.name

        try:
            inputs = preflight_check.extract_workflow_inputs(f_path)
            self.assertEqual(inputs, ["mode", "pr-number"])
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_preflight_checks_pass(self):
        """Integration test: verify preflight checks pass against the real repo."""
        self.assertTrue(preflight_check.check_changelog_fragments())
        self.assertTrue(preflight_check.check_action_docs_sync())


if __name__ == "__main__":
    unittest.main()
