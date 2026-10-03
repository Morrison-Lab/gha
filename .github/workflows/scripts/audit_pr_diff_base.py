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

**Every string in the workflow is audited, not only a key named
``base-ref``.**  The same SHA reaches a checker as ``base-ref:``, as an
``env:`` variable at any level, interpolated into a ``run:`` script, or
indirectly through a matrix value or a job output, and ``_selftest.yml`` used
three of those spellings before gha#1007.  Only the ``on:`` block and the
workflow's display names are skipped, since neither feeds a step.

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

# Whitespace-tolerant, and case-insensitive because GitHub's expression
# property names are. Bracketed string access (`github['event']...`) is
# rewritten to dots by `_normalise` first, so either spelling matches.
BASE_SHA = re.compile(
    r"github\s*\.\s*event\s*\.\s*pull_request\s*\.\s*base\s*\.\s*sha\b",
    re.IGNORECASE,
)
_BRACKET = re.compile(r"\[\s*['\"]([A-Za-z0-9_-]+)['\"]\s*\]")


def _normalise(text: str) -> str:
    return _BRACKET.sub(r".\1", text)


def _require_mapping(path: pathlib.Path, where: str, block) -> None:
    if block is not None and not isinstance(block, dict):
        raise Unparsable(f"{path}: {where} is {type(block).__name__}, not a mapping")


def _walk(value, where: str):
    """Yield ``(location, string)`` for every string under ``value``."""
    if isinstance(value, str):
        yield where, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{where}[{index}]")


def _is_checkout(step) -> bool:
    uses = step.get("uses")
    return isinstance(uses, str) and uses.split("@", 1)[0] == "actions/checkout"


# Top-level keys that never feed a step: the trigger block (which PyYAML
# parses `on:` as the boolean True) and display names.
_SKIPPED_TOP_LEVEL = {"on", True, "name", "run-name"}


def violations(path: pathlib.Path, doc) -> list[str]:
    # Refuse malformed shapes before walking, so a block the audit could not
    # interpret is an error rather than a clean result.
    require_jobs(path, doc)
    _require_mapping(path, "workflow-level 'env'", doc.get("env"))
    list(iter_job_inputs(path, doc))
    exempt = set()
    for job_id, job in doc["jobs"].items():
        _require_mapping(path, f"job '{job_id}' 'env'", job.get("env"))
    for job_id, index, step in iter_steps(path, doc):
        for block_name in ("with", "env"):
            _require_mapping(
                path, f"job '{job_id}' step {index} '{block_name}'", step.get(block_name)
            )
        if _is_checkout(step) and "ref" in (step.get("with") or {}):
            exempt.add(f"jobs.{job_id}.steps[{index}].with.ref")

    # Every string anywhere else in the workflow: step inputs, env at any
    # level, run scripts, matrix values, job outputs, container env, `if:`.
    # A lagging SHA can reach a checker through any of them.
    found = []
    for key, value in doc.items():
        if key in _SKIPPED_TOP_LEVEL:
            continue
        for where, text in _walk(value, str(key)):
            if where not in exempt and BASE_SHA.search(_normalise(text)):
                found.append(f"{path}: '{where}' carries pull_request.base.sha")
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
