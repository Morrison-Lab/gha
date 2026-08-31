#!/usr/bin/env python3
"""Fail when a workflow passes SUBMODULES_TOKEN to any step's ``token:`` input.

That secret authenticates a cross-owner SUBMODULE fetch, via the
checkout-submodules composite's ``submodules-token:`` input, so it must never
gate the caller's own repo checkout (gha#442) --- a consumer that sets it
correctly for its own submodule is exactly the consumer whose main checkout
then fails, since the token has no reason to be able to read the caller's repo.

**Parsed, not grepped.**  The audit this replaces anchored a regex on a
line-leading ``token:``, which distinguished ``token:`` from
``submodules-token:`` only because the latter has a prefix before the colon.
Walking the parsed ``with:`` mapping tells the two apart by key rather than by
spelling, so neither indentation nor a reflowed value can confuse it, and
heredoc text inside a ``run:`` block is not reachable at all (gha#716).

**Deliberately NOT scoped to ``actions/checkout``.**  ``actions/checkout`` is
the canonical case and not the only one: any action handed this secret through
a ``token:`` input is being trusted to authenticate against the caller's own
repository, which is precisely what it cannot do.  Scoping the audit to a
single action name would also miss a fork, a wrapper composite, or a rename,
and the two errors are not symmetric --- a false negative ships a broken
checkout to a consumer, while a false positive is a one-line conversation on a
PR.  The reported line names the step's action so a genuine exception is
recognizable at a glance.

Usage::

    python3 audit_workflow_token_usage.py [--workflows-dir DIR]
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
    is_workflows_restored,
    iter_job_inputs,
    iter_steps,
    load_workflow,
    require_workflows,
)

SECRET = "SUBMODULES_TOKEN"

# GitHub resolves an action's inputs case-insensitively, so `Token:` and
# `token:` are the same input. Comparing case-sensitively would leave a
# one-keystroke bypass of this whole audit.
TOKEN_KEY = "token"

# The identifier, not a substring of one: `NOT_SUBMODULES_TOKEN` is a different
# secret, and blocking a workflow that uses it would be a false positive on a
# check whose whole value is that a failure means something.
SECRET_REF = re.compile(rf"\b{SECRET}\b")


def _reject_container(path: pathlib.Path, where: str, value) -> None:
    """Refuse a `token:` that is a list or mapping.

    An input value may legitimately be a string, number, or boolean, so those
    are left alone. A container is not a value any input takes, so it is a
    shape this audit did not evaluate rather than one it cleared.
    """
    if isinstance(value, (list, dict)):
        raise Unparsable(
            f"{path}: {where} is {type(value).__name__}, not a scalar"
        )


def violations(path: pathlib.Path, doc) -> list[str]:
    found = []
    # Job level first: a reusable-workflow caller passes values through `with:`
    # and `secrets:`, which no walk over `steps` can see.
    for job_id, block_name, key, value in iter_job_inputs(path, doc):
        if key.lower() != TOKEN_KEY:
            continue
        _reject_container(path, f"job '{job_id}' {block_name}.token", value)
        if isinstance(value, str) and SECRET_REF.search(value):
            found.append(
                f"{path}: job '{job_id}' passes {SECRET} as '{block_name}.token'"
            )
    for job_id, index, step in iter_steps(path, doc):
        with_block = step.get("with")
        if with_block is None:
            continue
        if not isinstance(with_block, dict):
            raise Unparsable(
                f"{path}: job '{job_id}' step {index} has 'with' as "
                f"{type(with_block).__name__}, not a mapping"
            )
        # Exactly the `token` key, case-insensitively. `submodules-token`
        # legitimately carries this secret and is a different key, so no prefix
        # or suffix matching --- but GitHub resolves an action's inputs
        # case-insensitively, so `Token:` is the same input and matching case
        # exactly would leave a one-keystroke bypass.
        value = next(
            (v for k, v in with_block.items() if str(k).lower() == TOKEN_KEY),
            None,
        )
        _reject_container(path, f"job '{job_id}' step {index} with.token", value)
        if isinstance(value, str) and SECRET_REF.search(value):
            action = step.get("uses")
            named = f" ({action})" if isinstance(action, str) else ""
            found.append(
                f"{path}: job '{job_id}' step {index}{named} passes {SECRET} "
                "to a 'token:' input"
            )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows-dir", default=".github/workflows", type=pathlib.Path)
    args = parser.parse_args(argv)

    if is_workflows_restored(args.workflows_dir):
        print(
            "::notice::Skipping audit-workflow-token-usage: .github/workflows/ "
            "was restored from default branch (gha#598, gha#765)."
        )
        return 0

    try:
        files = require_workflows(args.workflows_dir)
    except Discovery as exc:
        print(f"::error::audit-workflow-token-usage: {exc}", file=sys.stderr)
        return 2

    found = []
    for path in files:
        try:
            # The walk itself can raise, not just the parse -- see the sibling
            # audit's note.
            found.extend(violations(path, load_workflow(path)))
        except Unparsable as exc:
            print(f"::error::audit-workflow-token-usage: {exc}", file=sys.stderr)
            return 2

    if found:
        for line in found:
            print(line)
        print(
            "::error::A step above passes SUBMODULES_TOKEN to a 'token:' input "
            "(see gha#442). That secret authenticates a cross-owner submodule "
            "fetch and cannot authenticate against the caller's own "
            "repository, so no action may be handed it as a general-purpose "
            "token. Where the step is a checkout, use the checkout-submodules "
            "composite's 'submodules-token:' input instead."
        )
        return 1

    print(
        "No workflow passes SUBMODULES_TOKEN to a 'token:' input "
        f"({len(files)} file(s) examined)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
