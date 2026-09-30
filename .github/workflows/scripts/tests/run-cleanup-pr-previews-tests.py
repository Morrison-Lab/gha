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
import subprocess
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


def extract_jq_filter(workflow_path: pathlib.Path) -> str:
    content = workflow_path.read_text(encoding="utf-8")
    m = re.search(r"local jq_filter='(.*?)'", content, re.DOTALL)
    if not m:
        raise ValueError("Could not find jq_filter in cleanup-pr-previews.yml")
    return m.group(1).strip()


JQ_FILTER = extract_jq_filter(DEFAULT_WORKFLOW)


def matches_publish_workflow(name: str, wf_name: str, target_wf: str = "") -> bool:
    """Execute the exact jq filter from cleanup-pr-previews.yml via jq subprocess."""
    script = f"""
    {JQ_FILTER}
    def check($n; $w; $p):
      {{"name": $n, "workflowName": $w}} as $run
      | if ($run | is_preview) then false
        else (matches($n // ""; $p) or matches($w // ""; $p))
        end;
    check($name; $wf_name; $target)
    """
    proc = subprocess.run(
        [
            "jq",
            "-n",
            "--arg",
            "name",
            name or "",
            "--arg",
            "wf_name",
            wf_name or "",
            "--arg",
            "target",
            target_wf or "",
            script,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip() == "true"


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
        """Verify permissions block includes actions:read for gh run list (gha#994, gha#995)."""
        wf = load_yaml(DEFAULT_WORKFLOW)
        cleanup_job = wf.get("jobs", {}).get("cleanup", {})
        perms = cleanup_job.get("permissions", {})
        self.assertEqual(
            perms,
            {"contents": "write", "pull-requests": "read", "actions": "read"},
            "cleanup-pr-previews job permissions must include contents:write, pull-requests:read, actions:read",
        )

    def test_example_and_reference_consistency(self):
        example_text = DEFAULT_EXAMPLE.read_text(encoding="utf-8")
        ref_text = DEFAULT_REFERENCE.read_text(encoding="utf-8")

        self.assertIn("publish-workflow", example_text)
        self.assertIn("wait-for-publish", example_text)
        self.assertIn("actions: read", example_text)
        self.assertIn("`publish-workflow`", ref_text)
        self.assertIn("`wait-for-publish`", ref_text)
        self.assertIn("`actions: read`", ref_text)


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
        self.assertTrue(matches_publish_workflow("Quarto Publish", "quarto-publish.yml", "quarto-publish*"))
        self.assertFalse(matches_publish_workflow("Other Build", "build.yml", "quarto-publish*"))
        self.assertTrue(matches_publish_workflow("Custom Site Deploy", "custom.yml", "custom site deploy"))

    def test_unanchored_glob_substring_not_matched(self):
        """A glob like 'quarto-publish*' must NOT match 'not-quarto-publish-workflow' (Finding 3)."""
        self.assertFalse(
            matches_publish_workflow(
                "Not Quarto Publish Workflow",
                "not-quarto-publish-workflow.yml",
                "quarto-publish*",
            )
        )

    def test_unescaped_parentheses_and_brackets_do_not_crash_jq(self):
        """Names with parentheses or brackets must not crash jq (Finding 5)."""
        self.assertTrue(
            matches_publish_workflow(
                "Quarto Publish (website)",
                "quarto-publish.yml",
                "Quarto Publish (website)",
            )
        )
        self.assertTrue(
            matches_publish_workflow(
                "Quarto Publish [website]",
                "quarto-publish.yml",
                "Quarto Publish [website]",
            )
        )


class TestPruneStaleJqLogic(unittest.TestCase):
    def test_non_publish_commit_runs_do_not_match(self):
        """Non-publish workflows on commit must not count as matching publish workflows (Finding 1)."""
        runs = [
            {"workflowName": "selftest", "name": "selftest", "status": "completed", "conclusion": "success"},
            {"workflowName": "CodeQL", "name": "CodeQL", "status": "completed", "conclusion": "success"},
            {"workflowName": "Claude Code Review", "name": "Claude Code Review", "status": "completed", "conclusion": "skipped"},
        ]
        matching = [
            r for r in runs
            if matches_publish_workflow(r.get("name", ""), r.get("workflowName", ""))
        ]
        self.assertEqual(matching, [])

    def test_publish_commit_runs_matched(self):
        runs = [
            {"workflowName": "selftest", "name": "selftest", "status": "completed", "conclusion": "success"},
            {"workflowName": "Quarto Publish (website)", "name": "Quarto Publish (website)", "status": "completed", "conclusion": "success"},
        ]
        matching = [
            r for r in runs
            if matches_publish_workflow(r.get("name", ""), r.get("workflowName", ""))
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["workflowName"], "Quarto Publish (website)")

    def test_literal_pattern_does_not_substring_match(self):
        """A literal pattern without wildcards must not match unrelated names containing the substring (Finding 1)."""
        self.assertFalse(
            matches_publish_workflow(
                "Unpublished Draft Check",
                "unpublished-draft.yml",
                "publish",
            )
        )
        self.assertFalse(
            matches_publish_workflow(
                "Auto-undeploy Check",
                "auto-undeploy.yml",
                "Deploy",
            )
        )
        self.assertTrue(
            matches_publish_workflow(
                "Publish",
                "publish.yml",
                "publish",
            )
        )
        self.assertTrue(
            matches_publish_workflow(
                "Deploy",
                "deploy.yml",
                "deploy",
            )
        )
        self.assertTrue(
            matches_publish_workflow(
                "Deploy Website",
                "deploy.yml",
                "*deploy*",
            )
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestCleanupPrPreviewsContract)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestPublishWorkflowMatcher))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestPruneStaleJqLogic))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
