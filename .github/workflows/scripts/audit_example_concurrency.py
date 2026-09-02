#!/usr/bin/env python3
"""Fail when an example stub's top-level concurrency group collides with a
job-level group in the reusable workflow it calls (gha#809).

A caller-level ``concurrency:`` block and a nested job-level block naming the
same group deadlock GitHub Actions: the nested job fails with no runner, no
steps, and no log. gha#437 recorded that for the review family; gha#654 then
added ``group: gh-pages`` to ``quarto-publish.yml``'s deploy job without
touching ``examples/quarto-publish.yml``, which still told consumers to
declare the same group at the top level, and every publish run on a consumer
that copied it failed silently.

The population is every ``examples/*.yml`` stub, and the comparison is made
against the workflow each ``uses:`` actually names, so a job-level group added
later is caught the moment it lands rather than when the next consumer copies
the stub. A stub whose ``uses:`` names a workflow file this repo does not
carry is an error, not a skip: an audit that walks past it would report a
tree it never examined as clean.

Usage::

    python3 audit_example_concurrency.py [--examples DIR] [--workflows DIR]

Exit 0 when no stub collides, 1 on a collision, 2 on a malformed or missing
input.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from workflow_discovery import Unparsable, load_workflow, require_jobs  # noqa: E402

USES_RE = re.compile(r"^Morrison-Lab/gha/\.github/workflows/([^@/]+\.ya?ml)@")


def die(message: str) -> None:
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(2)


def load(path: pathlib.Path):
    """Parse with workflow_discovery's loader, so malformed input refuses the
    same way every other audit here refuses, rather than with a second copy of
    the rule (gha#809 review)."""
    try:
        doc = load_workflow(path)
        require_jobs(path, doc)
    except Unparsable as exc:
        die(str(exc))
    return doc


def group_of(block) -> str | None:
    """The group name of a ``concurrency:`` value, or None when absent."""
    if block is None:
        return None
    if isinstance(block, str):
        return block.strip()
    if isinstance(block, dict):
        group = block.get("group")
        return None if group is None else str(group).strip()
    die(f"concurrency block is {type(block).__name__}, expected a string or mapping")


def job_groups(path: pathlib.Path, doc) -> dict[str, str]:
    """Job name -> job-level concurrency group, for jobs that declare one."""
    jobs = require_jobs(path, doc)
    found: dict[str, str] = {}
    for name, job in jobs.items():
        if not isinstance(job, dict):
            die(f"{path}: job {name!r} is {type(job).__name__}, expected a mapping")
        group = group_of(job.get("concurrency"))
        if group is not None:
            found[str(name)] = group
    return found


def callee_files(path: pathlib.Path, doc) -> list[str]:
    jobs = require_jobs(path, doc)
    files: list[str] = []
    for name, job in jobs.items():
        if not isinstance(job, dict):
            die(f"{path}: job {name!r} is {type(job).__name__}, expected a mapping")
        uses = job.get("uses")
        if uses is None:
            continue
        if not isinstance(uses, str):
            die(f"{path}: job {name!r} uses: is {type(uses).__name__}, expected a string")
        match = USES_RE.match(uses)
        if match:
            files.append(match.group(1))
    return files


def audit(examples_dir: pathlib.Path, workflows_dir: pathlib.Path) -> list[str]:
    stubs = sorted(examples_dir.glob("*.yml")) + sorted(examples_dir.glob("*.yaml"))
    if not stubs:
        die(f"{examples_dir}: no example stubs found")
    findings: list[str] = []
    examined = 0
    for stub in stubs:
        doc = load(stub)
        top = group_of(doc.get("concurrency"))
        callees = callee_files(stub, doc)
        for callee in callees:
            wf = workflows_dir / callee
            if not wf.is_file():
                die(f"{stub}: uses {callee}, which is not in {workflows_dir}")
            examined += 1
            if top is None:
                continue
            for job, group in job_groups(wf, load(wf)).items():
                if group == top:
                    findings.append(
                        f"{stub}: top-level concurrency group {top!r} is also declared "
                        f"on job {job!r} of {callee}; the two deadlock (gha#809)"
                    )
    print(f"examined {len(stubs)} stub(s) against {examined} reusable-workflow call(s)")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default="examples")
    parser.add_argument("--workflows", default=".github/workflows")
    args = parser.parse_args()
    findings = audit(pathlib.Path(args.examples), pathlib.Path(args.workflows))
    for finding in findings:
        print(f"::error::{finding}")
    if findings:
        return 1
    print("no example stub collides with its called workflow's job-level concurrency group")
    return 0


if __name__ == "__main__":
    sys.exit(main())
