#!/usr/bin/env python3
"""Fail when a workflow references a third-party action not pinned to a SHA.

A floating ref (``@v4``, ``@main``) resolves to whatever that tag or branch
points at when the job runs, so the code executed is chosen by the action's
owner rather than by this repo (gha#328).  What makes a ref safe is that it
names content rather than a label: a 40-character Git commit SHA for a
repository action, or an ``@sha256:`` image digest for a ``docker://`` one.

Exempt:

* local refs (``./...``), which are this repo's own composites;
* ``Morrison-Lab/gha`` refs, which are this repo calling itself at a tag.

**Parsed, not grepped, and that is the point (gha#720).**  The audit this
replaces anchored on a line-leading ``uses:``, so it saw

    - name: Check out
      uses: actions/checkout@<sha>

and did not see ``- uses: actions/checkout@<sha>``, which left three real
references exempt --- all in ``altdoc-multiversion-docs.yml`` (measured
2026-08-28 against `main` at 7719d04).  Widening the regex was not the fix
either: it then also matched ``_selftest.yml``'s heredoc-written fixture
workflows, which are text inside a ``run:`` block rather than references
GitHub ever resolves.  A parsed walk sees both spellings by construction and cannot
see heredoc content at all.

Usage::

    python3 audit_workflow_action_pins.py [--workflows-dir DIR]
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
    iter_job_uses,
    iter_steps,
    load_workflow,
    require_workflows,
)

# A Git commit for a repository action, or an image digest for a `docker://`
# one --- GitHub accepts both spellings of `uses:`, and a digest is as immutable
# as a commit, so rejecting it would report a securely pinned action as unpinned.
SHA_PINNED = re.compile(r"@(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")
SELF_REPO = "Morrison-Lab/gha"


def is_exempt(uses: str) -> bool:
    """Local refs and this repo's own refs need no SHA.

    Both tests are anchored at a path boundary rather than a bare prefix: a
    plain `startswith(SELF_REPO)` would also exempt `Morrison-Lab/gha-evil`,
    which is a different repository under someone else's control, and the
    exemption exists precisely to say "this code is ours".
    """
    if uses == "." or uses.startswith("./") or uses.startswith("../"):
        return True
    return uses == SELF_REPO or uses.startswith(SELF_REPO + "/")


def violations(path: pathlib.Path, doc) -> list[str]:
    found = []
    for job_id, uses in iter_job_uses(path, doc):
        if not is_exempt(uses) and not SHA_PINNED.search(uses):
            found.append(f"{path}: job '{job_id}' calls '{uses}'")
    for job_id, index, step in iter_steps(path, doc):
        uses = step.get("uses")
        if uses is None:
            continue
        if not isinstance(uses, str):
            # Refused rather than skipped, matching iter_job_uses: a step whose
            # `uses` is a list or mapping is one this audit did not examine,
            # and reporting it as pinned would be a claim about a reference
            # nobody read.
            raise Unparsable(
                f"{path}: job '{job_id}' step {index} has 'uses' as "
                f"{type(uses).__name__}, not a string"
            )
        if not is_exempt(uses) and not SHA_PINNED.search(uses):
            found.append(f"{path}: job '{job_id}' step {index} uses '{uses}'")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows-dir", default=".github/workflows", type=pathlib.Path)
    args = parser.parse_args(argv)

    try:
        files = require_workflows(args.workflows_dir)
    except Discovery as exc:
        print(f"::error::audit-workflow-action-pins: {exc}", file=sys.stderr)
        return 2

    found = []
    for path in files:
        try:
            # The walk itself can raise, not just the parse: a malformed
            # `jobs`/`steps` shape means the audit examined nothing in that
            # file, which is not the same as finding nothing in it.
            found.extend(violations(path, load_workflow(path)))
        except Unparsable as exc:
            print(f"::error::audit-workflow-action-pins: {exc}", file=sys.stderr)
            return 2

    if found:
        for line in found:
            print(line)
        print(
            "::error::Unpinned third-party actions found in workflows (see "
            "gha#328); the offending references are listed above."
        )
        return 1

    print(f"All third-party actions in {len(files)} workflow file(s) are SHA-pinned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
