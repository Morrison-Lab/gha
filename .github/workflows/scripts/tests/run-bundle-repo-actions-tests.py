#!/usr/bin/env python3
"""Validates the bundled repository actions and workflows.

Checks:
- All 6 composite actions exist with valid YAML and runs.using == 'composite'
- All 6 reusable workflows exist with valid YAML and on.workflow_call
- All 6 example files exist in examples/
- All 6 reference pages exist in website/reference/ and are registered in website/_quarto.yml
- Input consistency between composite actions and reusable workflows
"""

import sys
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]

BUNDLED_CAPABILITIES = [
    "check-repo-hygiene",
    "check-quarto-website",
    "check-quarto-book",
    "check-quarto-manuscript",
    "check-r-package",
    "check-python-package",
]


def test_bundled_actions():
    failures = []
    quarto_yml_path = REPO_ROOT / "website" / "_quarto.yml"
    with open(quarto_yml_path, "r", encoding="utf-8") as f:
        quarto_yml = yaml.safe_load(f)
    quarto_text = quarto_yml_path.read_text(encoding="utf-8")

    for cap in BUNDLED_CAPABILITIES:
        # 1. Action exists and is valid composite
        action_path = REPO_ROOT / cap / "action.yml"
        if not action_path.exists():
            failures.append(f"Missing composite action: {action_path}")
            continue

        with open(action_path, "r", encoding="utf-8") as f:
            action_data = yaml.safe_load(f)

        if not action_data or action_data.get("runs", {}).get("using") != "composite":
            failures.append(f"{cap}/action.yml runs.using is not 'composite'")

        action_inputs = set(action_data.get("inputs", {}).keys())

        # 2. Reusable workflow exists and is workflow_call
        wf_path = REPO_ROOT / ".github" / "workflows" / f"{cap}.yml"
        if not wf_path.exists():
            failures.append(f"Missing reusable workflow: {wf_path}")
            continue

        with open(wf_path, "r", encoding="utf-8") as f:
            wf_data = yaml.safe_load(f)

        on_data = (wf_data.get("on") or wf_data.get(True) or {}) if wf_data else {}
        if not wf_data or "workflow_call" not in on_data:
            failures.append(f"{wf_path} does not declare 'on.workflow_call'")

        wf_inputs = set(
            on_data.get("workflow_call", {}).get("inputs", {}).keys()
        )

        # 3. Input parity check
        missing_in_wf = action_inputs - wf_inputs
        if missing_in_wf:
            failures.append(f"{cap}: action inputs not declared in workflow: {missing_in_wf}")

        # 4. Example file exists
        example_path = REPO_ROOT / "examples" / f"{cap}.yml"
        if not example_path.exists():
            failures.append(f"Missing example file: {example_path}")
        else:
            with open(example_path, "r", encoding="utf-8") as f:
                yaml.safe_load(f)

        # 5. Reference page exists
        ref_path = REPO_ROOT / "website" / "reference" / f"{cap}.qmd"
        if not ref_path.exists():
            failures.append(f"Missing reference documentation: {ref_path}")

        # 6. Sidebar registration
        ref_entry = f"reference/{cap}.qmd"
        if ref_entry not in quarto_text:
            failures.append(f"{ref_entry} is not registered in website/_quarto.yml")

        print(f"OK   {cap}: action, workflow, example, and reference doc valid")

    if failures:
        print("\nFailures:")
        for fail in failures:
            print(f"  ::error::{fail}")
        return 1

    print(f"\nAll {len(BUNDLED_CAPABILITIES)} bundled capabilities verified cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(test_bundled_actions())
