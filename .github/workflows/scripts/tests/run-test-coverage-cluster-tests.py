#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Assert the cluster-check contracts of the test-coverage reusable workflow.

The cluster job cannot run in this repo's selftest (it needs the cluster ssh
key), so what can go silently wrong is YAML shape: both coverage jobs running
at once, the cluster job not honouring `min-coverage`, a threshold compare
that passes on any value, or the report not being uploaded.

Usage::

    python3 run-test-coverage-cluster-tests.py
    python3 run-test-coverage-cluster-tests.py --self-test
"""

from __future__ import annotations

import pathlib
import sys

import yaml

WORKFLOW = pathlib.Path(__file__).resolve().parents[2] / "test-coverage.yml"

# The cluster job runs when the caller asks for it, or on a private repository
# whose CI_CLUSTER_CHECK variable is true (gha#1640).
ON = "inputs.cluster-check || (github.event.repository.private && vars.CI_CLUSTER_CHECK == 'true')"
TWO_HEADS = "cse-head.cluster.cs.wwu.edu csci-head.cluster.cs.wwu.edu"
THREE_HEADS = TWO_HEADS + " csci-lab-head.cs.wwu.edu:922"
IMAGE_FILE = "inputs.cluster-image-file || vars.CI_CLUSTER_RPKG_IMAGE_FILE"
HEAD = (
    f"${{{{ inputs.cluster-head || (({IMAGE_FILE}) != '' && '{THREE_HEADS}' || '{TWO_HEADS}') }}}}"
)


def check(text: str) -> list[str]:
    """Return the contract violations found in the workflow text."""
    doc = yaml.safe_load(text)
    jobs = doc["jobs"]
    inputs = doc[True]["workflow_call"]["inputs"]
    problems = []
    for name in ("cluster-check", "cluster-runs-on", "cluster-head", "cluster-image", "cluster-image-file"):
        if name not in inputs:
            problems.append(f"input {name} is missing")
    if jobs["test-coverage"].get("if", "") != f"${{{{ !({ON}) }}}}":
        problems.append("the runner job does not stand down when the cluster job runs")
    cluster = jobs.get("test-coverage-cluster", {})
    if cluster.get("if", "") != f"${{{{ {ON} }}}}":
        problems.append("the cluster job is not gated on cluster-check or CI_CLUSTER_CHECK")
    if inputs["cluster-check"].get("default") is not False:
        problems.append("input cluster-check must default to false")
    if inputs["cluster-head"].get("default") != "":
        problems.append("input cluster-head must default to empty, so jobs spread over the heads")
    steps = cluster.get("steps", [])
    uses = [s.get("uses", "") for s in steps]
    batch = [s for s in steps if "actions/condor-batch@" in s.get("uses", "")]
    if not batch:
        problems.append("the cluster job does not call condor-batch")
    else:
        args = batch[0].get("with", {})
        if args.get("head") != HEAD:
            problems.append(f"condor-batch head is not the default-heads expression: {args.get('head')!r}")
        if args.get("image") != "${{ inputs.cluster-image || vars.CI_CLUSTER_RPKG_IMAGE }}":
            problems.append("condor-batch image does not fall back to CI_CLUSTER_RPKG_IMAGE")
        if args.get("image-file") != f"${{{{ {IMAGE_FILE} }}}}":
            problems.append("condor-batch image-file does not fall back to CI_CLUSTER_RPKG_IMAGE_FILE")
    codecov = [i for i, u in enumerate(uses) if "codecov/codecov-action@" in u]
    threshold = [i for i, s in enumerate(steps) if "MIN_COVERAGE" in s.get("run", "")]
    if not codecov:
        problems.append("the cluster job does not upload the report to Codecov")
    else:
        args = steps[codecov[0]].get("with", {})
        if args.get("files") != "./coverage/cobertura.xml":
            problems.append(f"the Codecov upload does not read the cluster report: {args.get('files')!r}")
        if args.get("token") != "${{ secrets.CODECOV_TOKEN }}":
            problems.append("the Codecov upload does not pass CODECOV_TOKEN")
        if threshold and codecov[0] > threshold[0]:
            problems.append("the Codecov upload must come before the threshold, so a miss still publishes")
    if not any("upload-artifact@" in u for u in uses):
        problems.append("the cluster job does not upload the report")
    runs = "\n".join(s.get("run", "") for s in steps)
    if "MIN_COVERAGE" not in runs or "exit 1" not in runs:
        problems.append("the cluster job does not enforce min-coverage")
    if cluster.get("permissions") != {"contents": "read"}:
        problems.append("the cluster job needs exactly contents: read")
    return problems


def self_test(text: str) -> int:
    """Each mutation of the workflow must make `check` report a problem."""
    mutations = {
        "runner job always runs": (f"    if: ${{{{ !({ON}) }}}}\n", ""),
        "cluster job always runs": (f"    if: ${{{{ {ON} }}}}\n", ""),
        "variable ignored": ("vars.CI_CLUSTER_CHECK == 'true') }}\n    runs-on: ${{ inputs.cluster-runs-on",
                             "vars.CI_CLUSTER_CHECK == 'yes') }}\n    runs-on: ${{ inputs.cluster-runs-on"),
        "single head": (f"head: {HEAD}", "head: ${{ inputs.cluster-head }}"),
        "image variable dropped": ("inputs.cluster-image || vars.CI_CLUSTER_RPKG_IMAGE }}", "inputs.cluster-image }}"),
        "threshold dropped": ("exit 1", "exit 0"),
        "report not uploaded": ("upload-artifact@", "noop@"),
        "no Codecov upload": ("codecov/codecov-action@", "noop/noop@"),
        "Codecov reads the wrong file": ("files: ./coverage/cobertura.xml", "files: ./cobertura.xml"),
        "Codecov without the token": ("token: ${{ secrets.CODECOV_TOKEN }}\n          fail_ci_if_error",
                                      "token: ''\n          fail_ci_if_error"),
    }
    failures = 0
    for label, (old, new) in mutations.items():
        if old not in text:
            print(f"::error::mutation {label!r} did not apply")
            failures += 1
        elif not check(text.replace(old, new, 1)):
            print(f"::error::mutation {label!r} was not caught")
            failures += 1
    return failures


def main() -> int:
    text = WORKFLOW.read_text()
    problems = check(text)
    for p in problems:
        print(f"::error::{p}")
    failures = len(problems)
    if "--self-test" in sys.argv:
        failures += self_test(text)
    print(f"{failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
