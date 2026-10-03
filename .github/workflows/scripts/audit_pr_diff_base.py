#!/usr/bin/env python3
"""Fail when a workflow hands ``github.event.pull_request.base.sha`` to a step.

On ``pull_request``, ``actions/checkout`` checks out GitHub's merge ref, a
merge commit built on the base branch's CURRENT tip.  The payload's
``pull_request.base.sha`` can lag that tip by many commits, so a diff-scoped
check that diffs ``merge-base(base.sha, HEAD)..HEAD`` counts every commit the
base gained in between as added by the PR (gha#1007, measured in
Morrison-Lab/lds#184: 12 commits and 29 files the PR never touched).  The
base the checked-out tree was actually built from is ``HEAD^1``, the merge
commit's first parent, so that is what a diff base should be.

**Every value a step or a reusable-workflow call receives is audited, not
only a key named ``base-ref``.**  The same SHA reaches a checker as
``base-ref:``, as an ``env:`` variable (on the step, the job, or the whole
workflow, since steps inherit the last two), or interpolated into a ``run:``
script, and ``_selftest.yml`` used three of those spellings before gha#1007.

**One exemption: ``actions/checkout``'s ``ref:``.**  Checking out the base
commit itself, as ``version-check.yml`` does to read the base's version,
names a commit rather than diffing from it, so a lagging SHA there is the
commit the caller asked for.  Any other legitimate use (logging the SHA,
say) has no opt-out marker: read it from ``$GITHUB_EVENT_PATH`` inside the
script instead, which keeps the audit's verdict unambiguous.

**Scope.**  Workflow files only: ``.github/workflows`` by default, and
``_selftest.yml`` also runs it over ``examples/``.  Composite ``action.yml``
files are not scanned; none references the payload's base SHA today.
Matching is textual, so dotted and bracketed property access are both
caught, but an expression that never spells out ``base.sha``, such as
``toJSON(github.event.pull_request.base)``, is not.

Usage::

    python3 audit_pr_diff_base.py [--workflows-dir DIR]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from workflow_discovery import (  # noqa: E402
    Discovery,
    Unparsable,
    iter_job_inputs,
    iter_steps,
    load_workflow,
    require_jobs,
    require_workflows,
    skip_if_restored,
)

# Whitespace-tolerant. Bracketed string access (`github['event']...`) is
# rewritten to dots by `_normalise` first, so either spelling matches.
BASE_SHA = re.compile(
    r"github\s*\.\s*event\s*\.\s*pull_request\s*\.\s*base\s*\.\s*sha\b"
)
_BRACKET = re.compile(r"\[\s*['\"]([A-Za-z0-9_-]+)['\"]\s*\]")


def _normalise(text: str) -> str:
    return _BRACKET.sub(r".\1", text)


def _strings(value):
    """Yield every string inside a scalar, list, or mapping value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _mentions(value) -> bool:
    return any(BASE_SHA.search(_normalise(s)) for s in _strings(value))


def _env_block(path: pathlib.Path, where: str, block) -> dict:
    if block is None:
        return {}
    if not isinstance(block, dict):
        raise Unparsable(
            f"{path}: {where} 'env' is {type(block).__name__}, not a mapping"
        )
    return block


def _is_checkout(step) -> bool:
    uses = step.get("uses")
    return isinstance(uses, str) and uses.split("@", 1)[0] == "actions/checkout"


def violations(path: pathlib.Path, doc) -> list[str]:
    found = []
    jobs = require_jobs(path, doc)
    # Workflow- and job-level env reach every step through inheritance.
    for key, value in _env_block(path, "workflow", doc.get("env")).items():
        if _mentions(value):
            found.append(f"{path}: workflow-level 'env.{key}' carries pull_request.base.sha")
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue  # iter_job_inputs below refuses this shape
        for key, value in _env_block(path, f"job '{job_id}'", job.get("env")).items():
            if _mentions(value):
                found.append(f"{path}: job '{job_id}' 'env.{key}' carries pull_request.base.sha")
    for job_id, block_name, key, value in iter_job_inputs(path, doc):
        if _mentions(value):
            found.append(
                f"{path}: job '{job_id}' passes pull_request.base.sha as "
                f"'{block_name}.{key}'"
            )
    for job_id, index, step in iter_steps(path, doc):
        uses = step.get("uses")
        named = f" ({uses})" if isinstance(uses, str) else ""
        for block_name in ("with", "env"):
            block = step.get(block_name)
            if block is None:
                continue
            if not isinstance(block, dict):
                raise Unparsable(
                    f"{path}: job '{job_id}' step {index} has '{block_name}' "
                    f"as {type(block).__name__}, not a mapping"
                )
            for key, value in block.items():
                if block_name == "with" and str(key) == "ref" and _is_checkout(step):
                    continue
                if _mentions(value):
                    found.append(
                        f"{path}: job '{job_id}' step {index}{named} passes "
                        f"pull_request.base.sha as '{block_name}.{key}'"
                    )
        run = step.get("run")
        if isinstance(run, str) and _mentions(run):
            found.append(
                f"{path}: job '{job_id}' step {index} interpolates "
                "pull_request.base.sha into 'run'"
            )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows-dir", default=".github/workflows", type=pathlib.Path)
    args = parser.parse_args(argv)

    if skip_if_restored(args.workflows_dir, "audit-pr-diff-base"):
        return 0

    try:
        files = require_workflows(args.workflows_dir)
    except Discovery as exc:
        print(f"::error::audit-pr-diff-base: {exc}", file=sys.stderr)
        return 2

    found = []
    for path in files:
        try:
            found.extend(violations(path, load_workflow(path)))
        except Unparsable as exc:
            print(f"::error::audit-pr-diff-base: {exc}", file=sys.stderr)
            return 2

    if found:
        for line in found:
            print(line)
        print(
            "::error::A step above is handed pull_request.base.sha (see "
            "gha#1007). On pull_request the checkout is GitHub's merge ref, "
            "built on the base branch's current tip, and the payload's "
            "base.sha can lag that tip, so a diff from it counts the base's "
            "newer commits as added by the PR. Diff against 'HEAD^1', the "
            "merge commit's first parent, instead. To check out the base "
            "commit itself, pass it as actions/checkout's 'ref:', which is "
            "exempt."
        )
        return 1

    print(
        "No workflow hands pull_request.base.sha to a step as a diff base "
        f"({len(files)} file(s) examined)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
