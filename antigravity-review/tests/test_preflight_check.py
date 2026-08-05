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
            os.makedirs(workflow_dir)
            os.makedirs(doc_dir)

            wf_path = os.path.join(workflow_dir, "antigravity-code-review.yml")
            doc_path = os.path.join(doc_dir, "antigravity-code-review.qmd")

            with open(wf_path, "w", encoding="utf-8") as f:
                f.write("on:\n  workflow_call:\n    inputs:\n      mode:\n        type: string\n")

            with open(doc_path, "w", encoding="utf-8") as f:
                f.write("| `mode` | string |\n")

            with patch("os.path.abspath", return_value=tmp_dir):
                self.assertTrue(preflight_check.check_action_docs_sync())

            # Missing doc case
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write("| `other` | string |\n")

            with patch("os.path.abspath", return_value=tmp_dir):
                self.assertFalse(preflight_check.check_action_docs_sync())


if __name__ == "__main__":
    unittest.main()
