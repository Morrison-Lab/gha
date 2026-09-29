#!/usr/bin/env python3
"""Assert load-bearing contracts of the quarto-publish reusable workflow and composite action.

Usage:
    python3 run-quarto-publish-workflow-tests.py
    python3 run-quarto-publish-workflow-tests.py --self-test
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import tempfile

try:
    import yaml
except ImportError:
    print(
        "::error::PyYAML is required to run quarto-publish workflow tests.",
        file=sys.stderr,
    )
    sys.exit(1)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
DEFAULT_COMPOSITE = REPO_ROOT / "quarto-publish" / "action.yml"
DEFAULT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "quarto-publish.yml"

EXPECTED_COMPOSITE_INPUTS = (
    "path",
    "setup-r",
    "r-packages",
    "use-renv",
    "install-package",
    "setup-chrome",
    "tinytex",
    "setup-julia",
    "julia-version",
    "apt-packages",
    "output-dir",
    "render-profile",
    "formats",
    "freeze-cache",
    "deno-v8-options",
    "fail-on-render-warning",
    "forbid-log-patterns",
)

EXPECTED_WORKFLOW_INPUTS = EXPECTED_COMPOSITE_INPUTS + (
    "checkout-submodules",
    "pre-render-artifact",
    "pre-render-artifact-path",
    "deploy",
)


def check_quarto_publish(
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
    for inp in EXPECTED_COMPOSITE_INPUTS:
        if inp not in comp_inputs:
            errors.append(f"quarto-publish/action.yml is missing input '{inp}'")

    # 2. Check workflow inputs
    wf_triggers = workflow_doc.get(True, workflow_doc.get("on", {}))
    wf_call = (
        wf_triggers.get("workflow_call", {})
        if isinstance(wf_triggers, dict)
        else {}
    )
    wf_inputs = wf_call.get("inputs", {})
    for inp in EXPECTED_WORKFLOW_INPUTS:
        if inp not in wf_inputs:
            errors.append(
                f".github/workflows/quarto-publish.yml is missing input '{inp}'"
            )

    # 3. Check default agreement for setup-julia and julia-version
    if (
        str(comp_inputs.get("setup-julia", {}).get("default", "")).lower()
        != "false"
    ):
        errors.append("quarto-publish/action.yml setup-julia default is not 'false'")
    if (
        str(wf_inputs.get("setup-julia", {}).get("default", "")).lower()
        != "false"
    ):
        errors.append(
            ".github/workflows/quarto-publish.yml setup-julia default is not false"
        )
    if str(comp_inputs.get("julia-version", {}).get("default", "")) != "1":
        errors.append("quarto-publish/action.yml julia-version default is not '1'")
    if str(wf_inputs.get("julia-version", {}).get("default", "")) != "1":
        errors.append(
            ".github/workflows/quarto-publish.yml julia-version default is not '1'"
        )

    # 4. Check forwarding in quarto-publish.yml render step
    build_job = workflow_doc.get("jobs", {}).get("build", {})
    steps = build_job.get("steps", [])
    render_step = None
    for step in steps:
        uses = str(step.get("uses", ""))
        if "quarto-publish" in uses:
            render_step = step
            break
    if not render_step:
        errors.append(".github/workflows/quarto-publish.yml missing Render site step")
    else:
        with_args = render_step.get("with", {})
        for inp in EXPECTED_COMPOSITE_INPUTS:
            if inp not in with_args:
                errors.append(
                    f".github/workflows/quarto-publish.yml does not forward input '{inp}' in with:"
                )

    # 5. Ensure Julia setup pairs with julia-actions/cache (gha#974)
    comp_steps = composite_doc.get("runs", {}).get("steps", [])
    julia_setup_step = None
    julia_cache_step = None
    for step in comp_steps:
        uses = str(step.get("uses", ""))
        if "julia-actions/setup-julia" in uses:
            julia_setup_step = step
        elif "julia-actions/cache" in uses:
            julia_cache_step = step

    if not julia_setup_step:
        errors.append("quarto-publish/action.yml missing julia-actions/setup-julia step")
    if not julia_cache_step:
        errors.append(
            "quarto-publish/action.yml is missing julia-actions/cache step (gha#974)"
        )
    else:
        jc_if = str(julia_cache_step.get("if", ""))
        if "inputs.setup-julia == 'true'" not in jc_if:
            errors.append(
                f"quarto-publish/action.yml julia-actions/cache step missing setup-julia condition (got {jc_if!r})"
            )
        cache_name = str(julia_cache_step.get("with", {}).get("cache-name", ""))
        if "inputs.julia-version" not in cache_name:
            errors.append(
                f"quarto-publish/action.yml julia-actions/cache step cache-name must include inputs.julia-version (got {cache_name!r})"
            )

    return errors


def run_self_test() -> int:
    print("Running self-test mutations for quarto-publish...")
    baseline_composite = DEFAULT_COMPOSITE.read_text(encoding="utf-8")
    baseline_workflow = DEFAULT_WORKFLOW.read_text(encoding="utf-8")

    mutations = [
        (
            "drop setup-julia input in action.yml",
            DEFAULT_COMPOSITE,
            baseline_composite.replace("setup-julia:", "ignored-julia:"),
            DEFAULT_WORKFLOW,
            baseline_workflow,
        ),
        (
            "drop julia-version input in quarto-publish.yml",
            DEFAULT_COMPOSITE,
            baseline_composite,
            DEFAULT_WORKFLOW,
            baseline_workflow.replace("julia-version:", "ignored-julia-version:"),
        ),
        (
            "drop setup-julia forwarding in quarto-publish.yml",
            DEFAULT_COMPOSITE,
            baseline_composite,
            DEFAULT_WORKFLOW,
            baseline_workflow.replace(
                "setup-julia: ${{ inputs.setup-julia }}", ""
            ),
        ),
        (
            "drop setup-julia in action.yml",
            DEFAULT_COMPOSITE,
            baseline_composite.replace("uses: julia-actions/setup-julia", "uses: ignore/setup-julia"),
            DEFAULT_WORKFLOW,
            baseline_workflow,
        ),
        (
            "drop julia-actions/cache in action.yml",
            DEFAULT_COMPOSITE,
            baseline_composite.replace("uses: julia-actions/cache", "uses: ignore/cache"),
            DEFAULT_WORKFLOW,
            baseline_workflow,
        ),
        (
            "drop julia-version from julia cache-name in action.yml",
            DEFAULT_COMPOSITE,
            baseline_composite.replace("julia=${{ inputs.julia-version }};", ""),
            DEFAULT_WORKFLOW,
            baseline_workflow,
        ),
        (
            "drop setup-julia condition from julia cache in action.yml",
            DEFAULT_COMPOSITE,
            baseline_composite.replace("inputs.setup-julia == 'true'", "true"),
            DEFAULT_WORKFLOW,
            baseline_workflow,
        ),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = pathlib.Path(tmpdir)
        c_path = tmppath / "action.yml"
        w_path = tmppath / "quarto-publish.yml"

        for name, c_src, c_content, w_src, w_content in mutations:
            c_path.write_text(c_content, encoding="utf-8")
            w_path.write_text(w_content, encoding="utf-8")
            errors = check_quarto_publish(c_path, w_path)
            if not errors:
                print(f"FAIL: Mutation '{name}' was not caught!", file=sys.stderr)
                return 1
            print(f"OK: Mutation '{name}' caught ({len(errors)} error(s))")

    print("All quarto-publish self-test mutations caught successfully!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mutations against temporary copies.",
    )
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from workflow_discovery import skip_if_restored

    if skip_if_restored(DEFAULT_WORKFLOW.parent, "quarto-publish workflow tests"):
        return 0

    errors = check_quarto_publish()
    if errors:
        for err in errors:
            print(f"::error::{err}", file=sys.stderr)
        return 1

    print("OK: All quarto-publish workflow contract checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
