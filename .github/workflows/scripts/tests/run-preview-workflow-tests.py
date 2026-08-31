#!/usr/bin/env python3
"""Assert load-bearing contracts of the preview reusable workflow and composite action.

Usage:
    python3 run-preview-workflow-tests.py
    python3 run-preview-workflow-tests.py --self-test
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import tempfile

try:
    import yaml
except ImportError:
    print(
        "::error::PyYAML is required to run preview workflow tests.",
        file=sys.stderr,
    )
    sys.exit(1)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
DEFAULT_COMPOSITE = REPO_ROOT / "preview" / "action.yml"
DEFAULT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "preview.yml"
DEFAULT_EXAMPLE = REPO_ROOT / "examples" / "preview.yml"

EXPECTED_INPUTS = (
    "path",
    "r-version",
    "apt-packages",
    "use-renv",
    "r-packages",
    "install-package",
    "setup-chrome",
    "tinytex",
    "submodules",
    "render-profile",
    "output-dir",
    "formats",
    "fail-on-render-warning",
    "forbid-log-patterns",
    "detect-changed-chapters",
    "changed-chapters-banner",
    "changed-chapters-glob",
    "deployed-branch",
    "deployed-subdir",
    "changed-chapters-normalize-patterns",
    "banner-index",
)


def load_yaml(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def check_preview(
    composite_path: pathlib.Path = DEFAULT_COMPOSITE,
    workflow_path: pathlib.Path = DEFAULT_WORKFLOW,
) -> list[str]:
    errors: list[str] = []

    composite_text = composite_path.read_text(encoding="utf-8")
    workflow_text = workflow_path.read_text(encoding="utf-8")

    composite_doc = yaml.safe_load(composite_text)
    workflow_doc = yaml.safe_load(workflow_text)

    # 1. Check composite inputs
    comp_inputs = composite_doc.get("inputs", {})
    for inp in EXPECTED_INPUTS:
        if inp not in comp_inputs:
            errors.append(f"preview/action.yml is missing input '{inp}'")

    # 2. Check workflow inputs
    wf_triggers = workflow_doc.get(True, workflow_doc.get("on", {}))
    wf_call = (
        wf_triggers.get("workflow_call", {})
        if isinstance(wf_triggers, dict)
        else {}
    )
    wf_inputs = wf_call.get("inputs", {})
    for inp in EXPECTED_INPUTS:
        if inp not in wf_inputs:
            errors.append(
                f".github/workflows/preview.yml is missing input '{inp}'"
            )

    # 3. Check default agreement for tinytex and formats
    if (
        str(comp_inputs.get("tinytex", {}).get("default", "")).lower()
        != "false"
    ):
        errors.append("preview/action.yml tinytex default is not 'false'")
    if (
        str(wf_inputs.get("tinytex", {}).get("default", "")).lower()
        != "false"
    ):
        errors.append(".github/workflows/preview.yml tinytex default is not false")
    if comp_inputs.get("formats", {}).get("default", None) != "":
        errors.append("preview/action.yml formats default is not empty string")
    if wf_inputs.get("formats", {}).get("default", None) != "":
        errors.append(
            ".github/workflows/preview.yml formats default is not empty string"
        )

    # 4. Check forwarding in preview.yml step
    build_job = workflow_doc.get("jobs", {}).get("build", {})
    steps = build_job.get("steps", [])
    build_step = None
    for step in steps:
        if step.get("id") == "build" or "preview" in str(step.get("uses", "")):
            build_step = step
            break
    if not build_step:
        errors.append(".github/workflows/preview.yml missing Build preview step")
    else:
        with_args = build_step.get("with", {})
        for inp in EXPECTED_INPUTS:
            if inp not in with_args:
                errors.append(
                    f".github/workflows/preview.yml does not forward input '{inp}' in with:"
                )

    # 5. Check TinyTeX OR conditions in composite action
    setup_tinytex_marker = (
        "tinytex: ${{ inputs.tinytex == 'true' || "
        "contains(github.event.pull_request.labels.*.name, 'preview:pdf') }}"
    )
    if setup_tinytex_marker not in composite_text:
        errors.append(
            "preview/action.yml Quarto setup step does not have OR condition for tinytex"
        )

    pkg_tinytex_marker = (
        "inputs.tinytex == 'true' || "
        "contains(github.event.pull_request.labels.*.name, 'preview:pdf')"
    )
    if pkg_tinytex_marker not in composite_text:
        errors.append(
            "preview/action.yml TinyTeX packages step missing OR condition for tinytex"
        )

    # 6. Check render site logic handles formats input
    if "FORMATS: ${{ inputs.formats }}" not in composite_text:
        errors.append("preview/action.yml Render step missing FORMATS env var")
    if "TINYTEX: ${{ inputs.tinytex }}" not in composite_text:
        errors.append("preview/action.yml Render step missing TINYTEX env var")
    if 'elif [ "$FORMATS" = "default" ]; then' not in composite_text:
        errors.append(
            "preview/action.yml Render step missing bare render handler for formats: 'default'"
        )

    return errors


def run_self_test() -> int:
    print("Running self-test mutations...")
    baseline_composite = DEFAULT_COMPOSITE.read_text(encoding="utf-8")
    baseline_workflow = DEFAULT_WORKFLOW.read_text(encoding="utf-8")

    mutations = [
        (
            "drop tinytex OR condition in Quarto setup",
            DEFAULT_COMPOSITE,
            baseline_composite.replace("inputs.tinytex == 'true' || ", ""),
            DEFAULT_WORKFLOW,
            baseline_workflow,
        ),
        (
            "drop formats input in preview.yml",
            DEFAULT_COMPOSITE,
            baseline_composite,
            DEFAULT_WORKFLOW,
            re.sub(
                r"\s+formats:\s*\n\s+description:[^\n]+\n\s+type: string\n\s+default: ''",
                "",
                baseline_workflow,
            ),
        ),
        (
            "drop tinytex forwarding in preview.yml",
            DEFAULT_COMPOSITE,
            baseline_composite,
            DEFAULT_WORKFLOW,
            baseline_workflow.replace("tinytex: ${{ inputs.tinytex }}", ""),
        ),
        (
            "break tinytex default in action.yml",
            DEFAULT_COMPOSITE,
            baseline_composite.replace("default: 'false'", "default: 'true'", 1),
            DEFAULT_WORKFLOW,
            baseline_workflow,
        ),
        (
            "drop default bare render handler",
            DEFAULT_COMPOSITE,
            baseline_composite.replace(
                'elif [ "$FORMATS" = "default" ]; then', "elif false; then"
            ),
            DEFAULT_WORKFLOW,
            baseline_workflow,
        ),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = pathlib.Path(tmpdir)
        c_path = tmppath / "action.yml"
        w_path = tmppath / "preview.yml"

        for name, c_src, c_content, w_src, w_content in mutations:
            c_path.write_text(c_content, encoding="utf-8")
            w_path.write_text(w_content, encoding="utf-8")
            errors = check_preview(c_path, w_path)
            if not errors:
                print(
                    f"::error::Mutation '{name}' did not trigger any errors!",
                    file=sys.stderr,
                )
                return 1
            print(f"OK: Mutation '{name}' caught ({len(errors)} error(s))")

    print("All self-test mutations caught successfully!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test", action="store_true", help="Run mutation self-tests"
    )
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    errors = check_preview()
    if errors:
        for err in errors:
            print(f"::error::{err}", file=sys.stderr)
        return 1

    print("OK: All preview workflow contract checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
