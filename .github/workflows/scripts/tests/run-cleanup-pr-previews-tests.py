#!/usr/bin/env python3
"""Assert load-bearing contracts of cleanup-pr-previews reusable workflow and its publish checks.

Usage:
    python3 run-cleanup-pr-previews-tests.py
    python3 run-cleanup-pr-previews-tests.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import unittest

try:
    import yaml
except ImportError:
    print(
        "::error::PyYAML is required to run cleanup-pr-previews workflow tests.",
        file=sys.stderr,
    )
    sys.exit(1)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
DEFAULT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "cleanup-pr-previews.yml"
DEFAULT_EXAMPLE = REPO_ROOT / "examples" / "cleanup-pr-previews.yml"
DEFAULT_REFERENCE = REPO_ROOT / "website" / "reference" / "cleanup-pr-previews.qmd"

EXPECTED_WORKFLOW_INPUTS = {
    "preview-dir": "string",
    "compact-history": "boolean",
    "publish-workflow": "string",
    "wait-for-publish": "boolean",
}


def load_yaml(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def matches_publish_workflow(name: str, wf_name: str, target_wf: str = "") -> bool:
    low_name = (name or "").lower()
    low_wf = (wf_name or "").lower()
    if "preview" in low_name or "preview" in low_wf:
        return False
    if target_wf:
        pattern = target_wf.lower()
        if "*" in pattern:
            regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
            return bool(re.search(regex, low_name) or re.search(regex, low_wf))
        return pattern in low_name or pattern in low_wf
    return any(k in low_name or k in low_wf for k in ("publish", "deploy", "pages-build-deployment"))


class TestCleanupPrPreviewsContract(unittest.TestCase):
    def test_workflow_inputs(self):
        wf = load_yaml(DEFAULT_WORKFLOW)
        on = wf.get(True, wf.get("on", {}))
        wf_call = on.get("workflow_call", {})
        inputs = wf_call.get("inputs", {})

        for name, expected_type in EXPECTED_WORKFLOW_INPUTS.items():
            self.assertIn(name, inputs, f"Missing input: {name}")
            self.assertEqual(
                inputs[name].get("type"),
                expected_type,
                f"Input {name} has incorrect type",
            )

        self.assertEqual(inputs["wait-for-publish"].get("default"), True)
        self.assertEqual(inputs["publish-workflow"].get("default"), "")

    def test_permissions_are_not_widened(self):
        """Widening permissions breaks existing callers at parse time (gha#685, versioning.qmd)."""
        wf = load_yaml(DEFAULT_WORKFLOW)
        cleanup_job = wf.get("jobs", {}).get("cleanup", {})
        perms = cleanup_job.get("permissions", {})
        self.assertEqual(
            perms,
            {"contents": "write", "pull-requests": "read"},
            "cleanup-pr-previews job permissions must remain strictly contents:write and pull-requests:read",
        )

    def test_example_and_reference_consistency(self):
        example_text = DEFAULT_EXAMPLE.read_text(encoding="utf-8")
        ref_text = DEFAULT_REFERENCE.read_text(encoding="utf-8")

        self.assertIn("publish-workflow", example_text)
        self.assertIn("wait-for-publish", example_text)
        self.assertIn("`publish-workflow`", ref_text)
        self.assertIn("`wait-for-publish`", ref_text)


class TestPublishWorkflowMatcher(unittest.TestCase):
    def test_auto_detect_matches_publish_and_deploy(self):
        self.assertTrue(matches_publish_workflow("Quarto Publish (website)", "Quarto Publish (website)"))
        self.assertTrue(matches_publish_workflow("Deploy Website", "deploy-website.yml"))
        self.assertTrue(matches_publish_workflow("pages build and deployment", "pages-build-deployment"))

    def test_auto_detect_excludes_preview(self):
        self.assertFalse(matches_publish_workflow("Website Preview Deploy", "Website Preview Deploy"))
        self.assertFalse(matches_publish_workflow("Deploy preview for PR", "preview-deploy.yml"))
        self.assertFalse(matches_publish_workflow("PR Preview Publish", "preview.yml"))

    def test_custom_target_workflow_pattern(self):
        self.assertTrue(matches_publish_workflow("Quarto Publish Docs", "publish.yml", "quarto publish*"))
        self.assertTrue(matches_publish_workflow("Quarto Publish", "quarto-publish.yml", "quarto-publish.yml"))
        self.assertFalse(matches_publish_workflow("Other Build", "build.yml", "quarto-publish*"))
        self.assertTrue(matches_publish_workflow("Custom Site Deploy", "custom.yml", "custom site deploy"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestCleanupPrPreviewsContract)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestPublishWorkflowMatcher))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
