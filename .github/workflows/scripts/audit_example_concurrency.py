#!/usr/bin/env python3
"""Fail when an example stub's concurrency group collides with a job-level
group in the reusable workflow it calls (gha#809).

A caller-level ``concurrency:`` block and a nested job-level block naming the
same group deadlock GitHub Actions: the nested job fails with no runner, no
steps, and no log. Caller-level means either placement -- a top-level block,
or a block on the calling job itself, which is valid on a job that ``uses:`` a
reusable workflow and deadlocks identically (gha#811 review). A group on some
other job of the stub is not a collision: it serializes those two jobs and
never waits on the callee. gha#437 recorded that for the review family; gha#654 then
added ``group: gh-pages`` to ``quarto-publish.yml``'s deploy job without
touching ``examples/quarto-publish.yml``, which still told consumers to
declare the same group at the top level, and every publish run on a consumer
that copied it failed silently.

The population is every ``examples/*.yml`` and ``examples/*.yaml`` stub, and
the comparison is made
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


def group_of(path: pathlib.Path, where: str, block) -> str | None:
    """The group name of a ``concurrency:`` value, or None when absent.

    Present but malformed refuses (exit 2) rather than reading as absent: a
    mapping with no ``group``, an empty group name, or a ``group`` that is not
    a scalar is a broken stub that a consumer would copy, and an audit that
    walked past it would report clean over a file it never evaluated (Copilot
    on gha#811, two rounds).

    A list or mapping ``group`` is refused rather than stringified: ``str()``
    turns ``[a, b]`` into ``"[\'a\', \'b\']"``, a name no workflow can
    collide with, so the stub would pass an audit whose whole job is to refuse
    what it cannot evaluate. An INTEGER is accepted, since YAML parses an
    unquoted ``group: 2026`` that way and ``str()`` round-trips it exactly.
    A boolean or float is refused instead: Python renders those differently
    from GitHub (``True`` against ``true``, ``1.1`` against ``1.10``), so
    accepting one would compare a name that cannot match its real
    counterpart (gha#811 review).
    """
    if block is None:
        return None
    if isinstance(block, str):
        group = block.strip()
    elif isinstance(block, dict):
        raw = block.get("group")
        if raw is None:
            group = ""
        elif isinstance(raw, (bool, float)):
            # Refused rather than accepted: Python renders these differently
            # from GitHub, so the audit would compare a name that cannot match
            # its real counterpart. `bool` is listed first because it
            # subclasses `int`, so an `int` test would swallow it.
            die(f"{path}: {where} concurrency group is {type(raw).__name__}, "
                f"which does not round-trip; quote it")
        elif isinstance(raw, (str, int)):
            group = str(raw).strip()
        else:
            die(f"{path}: {where} concurrency group is {type(raw).__name__}, expected a scalar")
    else:
        die(f"{path}: {where} concurrency is {type(block).__name__}, expected a string or mapping")
    if not group:
        die(f"{path}: {where} concurrency names no group")
    return group


def job_groups(path: pathlib.Path, doc) -> dict[str, str]:
    """Job name -> job-level concurrency group, for jobs that declare one."""
    jobs = require_jobs(path, doc)
    found: dict[str, str] = {}
    for name, job in jobs.items():
        if not isinstance(job, dict):
            die(f"{path}: job {name!r} is {type(job).__name__}, expected a mapping")
        group = group_of(path, f"job {name!r}", job.get("concurrency"))
        if group is not None:
            found[str(name)] = group
    return found


def callee_calls(path: pathlib.Path, doc) -> list[tuple[str, str]]:
    """(calling job name, callee workflow filename) per reusable-workflow call.

    The job name is carried alongside the filename because a concurrency group
    on the calling job deadlocks exactly as a top-level one does, and only that
    job's own group does -- a group on some OTHER job in the same stub merely
    serializes the two jobs (gha#811 review).
    """
    jobs = require_jobs(path, doc)
    calls: list[tuple[str, str]] = []
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
            calls.append((str(name), match.group(1)))
    return calls


def audit(examples_dir: pathlib.Path, workflows_dir: pathlib.Path) -> list[str]:
    stubs = sorted(examples_dir.glob("*.yml")) + sorted(examples_dir.glob("*.yaml"))
    if not stubs:
        die(f"{examples_dir}: no example stubs found")
    findings: list[str] = []
    compared = 0
    for stub in stubs:
        doc = load(stub)
        top = group_of(stub, "top-level", doc.get("concurrency"))
        stub_jobs = job_groups(stub, doc)
        for job, callee in callee_calls(stub, doc):
            wf = workflows_dir / callee
            if not wf.is_file():
                die(f"{stub}: uses {callee}, which is not in {workflows_dir}")
            # Both placements deadlock, so both are checked. A top-level block
            # covers the whole run and therefore covers the calling job; a
            # block on the calling job itself is the same collision written
            # one level down, and it is syntactically valid on a job that
            # `uses:` a reusable workflow (gha#811 review).
            caller: list[tuple[str, str]] = []
            if top is not None:
                caller.append(("top-level", top))
            own = stub_jobs.get(job)
            if own is not None:
                caller.append((f"job {job!r}", own))
            if not caller:
                continue
            # Counted here rather than at the top of the loop: a call with no
            # caller-level group is walked past, not compared, and a summary
            # that counted it would read the same after the comparison was
            # gutted (gha#811 review).
            compared += 1
            callee_doc = load(wf)
            # The callee side has two placements too. A reusable workflow's own
            # top-level block applies to the calling job, so a caller group
            # matching it deadlocks exactly as a job-level one does --
            # `bump-dev-version.yml` is this repo's live example of a
            # workflow_call workflow carrying one (gha#811 review).
            callee_side = [
                (f"job {cjob!r}", cgroup)
                for cjob, cgroup in job_groups(wf, callee_doc).items()
            ]
            callee_top = group_of(wf, "top-level", callee_doc.get("concurrency"))
            if callee_top is not None:
                callee_side.append(("its top level", callee_top))
            for cwhere, cgroup in callee_side:
                for where, group in caller:
                    if cgroup == group:
                        findings.append(
                            f"{stub}: {where} concurrency group {group!r} is also "
                            f"declared on {cwhere} of {callee}; the two "
                            f"deadlock (gha#809)"
                        )
    print(
        f"examined {len(stubs)} stub(s); compared {compared} reusable-workflow "
        f"call(s) carrying a caller-level concurrency group"
    )
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
    print("no example stub collides with a concurrency group of the workflow it calls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
