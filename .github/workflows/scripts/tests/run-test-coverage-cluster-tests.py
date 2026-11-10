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


def check(text: str) -> list[str]:
    """Return the contract violations found in the workflow text."""
    doc = yaml.safe_load(text)
    jobs = doc["jobs"]
    inputs = doc[True]["workflow_call"]["inputs"]
    problems = []
    for name in ("cluster-check", "cluster-runs-on", "cluster-head", "cluster-image", "cluster-image-file"):
        if name not in inputs:
            problems.append(f"input {name} is missing")
    if "!inputs.cluster-check" not in jobs["test-coverage"].get("if", ""):
        problems.append("the runner job does not stand down when cluster-check is true")
    cluster = jobs.get("test-coverage-cluster", {})
    if "inputs.cluster-check" not in cluster.get("if", ""):
        problems.append("the cluster job is not gated on cluster-check")
    steps = cluster.get("steps", [])
    uses = [s.get("uses", "") for s in steps]
    if not any("actions/condor-batch@" in u for u in uses):
        problems.append("the cluster job does not call condor-batch")
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
        "runner job always runs": ("    if: ${{ !inputs.cluster-check }}\n", ""),
        "cluster job always runs": ("    if: ${{ inputs.cluster-check }}\n", ""),
        "threshold dropped": ("exit 1", "exit 0"),
        "report not uploaded": ("upload-artifact@", "noop@"),
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
