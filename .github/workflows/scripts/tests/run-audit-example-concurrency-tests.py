#!/usr/bin/env python3
"""Offline cases for audit_example_concurrency.py (gha#809).

Each case builds a throwaway examples/ and workflows/ pair, so the cases can
name a collision this repo's own tree must never carry. The negative cases
are the ones to keep if the suite is trimmed: a stub with no top-level block,
a stub whose group differs from the job's, and a callee with no job-level
group must all pass, or the audit would fail every stub the moment any
workflow gained a concurrency block.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "audit_example_concurrency.py"

STUB = """name: X
on: push
{top}
jobs:
  publish:
    uses: Morrison-Lab/gha/.github/workflows/{callee}@v2
"""
WORKFLOW = """name: Y
on: workflow_call
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo build
  deploy:
{conc}
    runs-on: ubuntu-latest
    steps:
      - run: echo deploy
"""
TOP_GH = "concurrency:\n  group: gh-pages\n  cancel-in-progress: false"
JOB_GH = "    concurrency:\n      group: gh-pages\n      cancel-in-progress: false"

# A stub whose CALLING job carries the concurrency block, rather than the run.
# GitHub accepts `concurrency:` on a job that `uses:` a reusable workflow, and
# the deadlock is identical -- gha#811 review reproduced it against the live
# tree, where the audit exited 0.
JOB_STUB = """name: X
on: push
jobs:
  publish:
    concurrency:
      group: {group}
      cancel-in-progress: false
    uses: Morrison-Lab/gha/.github/workflows/{callee}@v2
"""

# The group sits on a job that is NOT the caller. That serializes those two
# jobs and never waits on the callee, so it must NOT be reported.
OTHER_JOB_STUB = """name: X
on: push
jobs:
  lint:
    concurrency:
      group: {group}
      cancel-in-progress: false
    runs-on: ubuntu-latest
    steps:
      - run: echo lint
  publish:
    uses: Morrison-Lab/gha/.github/workflows/{callee}@v2
"""


def run(stub: str | None, workflow: str | None, callee: str = "quarto-publish.yml"):
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        ex = root / "examples"
        wf = root / "workflows"
        ex.mkdir()
        wf.mkdir()
        if stub is not None:
            (ex / "quarto-publish.yml").write_text(stub)
        if workflow is not None:
            (wf / callee).write_text(workflow)
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--examples", str(ex), "--workflows", str(wf)],
            capture_output=True,
            text=True,
        )


def main() -> int:
    failures = 0

    def expect(label: str, result, code: int, needle: str | None = None) -> None:
        nonlocal failures
        blob = result.stdout + result.stderr
        if result.returncode != code or (needle and needle not in blob):
            print(f"::error::{label}: expected exit {code}"
                  f"{' mentioning ' + repr(needle) if needle else ''}, got {result.returncode}\n{blob}")
            failures += 1
        else:
            print(f"OK   {label}")

    expect("collision fails", run(STUB.format(top=TOP_GH, callee="quarto-publish.yml"),
                                   WORKFLOW.format(conc=JOB_GH)), 1, "deadlock")
    expect("no top-level block passes", run(STUB.format(top="", callee="quarto-publish.yml"),
                                             WORKFLOW.format(conc=JOB_GH)), 0)
    expect("different group passes", run(STUB.format(top="concurrency:\n  group: publish-${{ github.ref }}", callee="quarto-publish.yml"),
                                          WORKFLOW.format(conc=JOB_GH)), 0)
    expect("callee without job-level group passes", run(STUB.format(top=TOP_GH, callee="quarto-publish.yml"),
                                                         WORKFLOW.format(conc="")), 0)
    expect("string-form concurrency collides too", run(STUB.format(top="concurrency: gh-pages", callee="quarto-publish.yml"),
                                                        WORKFLOW.format(conc="    concurrency: gh-pages")), 1, "deadlock")
    # The comparison is general, not a hard-coded 'gh-pages': a collision on any
    # other name fails too (gha#809 review). Hard-coding the string turns this red.
    expect("differently-named collision fails", run(STUB.format(top="concurrency:\n  group: docs-deploy", callee="quarto-publish.yml"),
                                                     WORKFLOW.format(conc="    concurrency:\n      group: docs-deploy")), 1, "'docs-deploy'")
    # Copilot on gha#811: present-but-malformed refuses rather than reading as
    # absent, so a broken stub cannot pass as clean.
    expect("mapping without a group is an error", run(STUB.format(top="concurrency:\n  cancel-in-progress: false", callee="quarto-publish.yml"),
                                                     WORKFLOW.format(conc=JOB_GH)), 2, "names no group")
    expect("empty group string is an error", run(STUB.format(top="concurrency: '  '", callee="quarto-publish.yml"),
                                                 WORKFLOW.format(conc=JOB_GH)), 2, "names no group")
    # A non-scalar group is refused rather than stringified (Copilot on
    # gha#811 round 2): str([a, b]) is a name nothing can collide with, so the
    # stub would pass the very audit meant to refuse what it cannot evaluate.
    expect("list group is an error", run(STUB.format(top="concurrency:\n  group: [a, b]", callee="quarto-publish.yml"),
                                          WORKFLOW.format(conc=JOB_GH)), 2, "expected a scalar")
    expect("mapping group is an error", run(STUB.format(top="concurrency:\n  group: {}", callee="quarto-publish.yml"),
                                             WORKFLOW.format(conc=JOB_GH)), 2, "expected a scalar")
    # A number is a legitimate YAML spelling of a group name and is accepted.
    expect("numeric group is accepted", run(STUB.format(top="concurrency:\n  group: 2026", callee="quarto-publish.yml"),
                                             WORKFLOW.format(conc=JOB_GH)), 0)
    expect("missing callee is an error", run(STUB.format(top=TOP_GH, callee="quarto-publish.yml"), None), 2, "not in")
    expect("empty examples dir is an error", run(None, WORKFLOW.format(conc=JOB_GH)), 2, "no example stubs")
    expect("unparsable stub is an error", run("jobs: [\n", WORKFLOW.format(conc=JOB_GH)), 2, "examples/quarto-publish.yml")
    expect("stub with no jobs mapping is an error", run("name: X\non: push\n", WORKFLOW.format(conc=JOB_GH)), 2, "no 'jobs' mapping")
    # gha#811 review, finding 1: the collision written one level down.
    expect("job-level caller group collides", run(JOB_STUB.format(group="gh-pages", callee="quarto-publish.yml"),
                                                   WORKFLOW.format(conc=JOB_GH)), 1, "deadlock")
    expect("job-level caller group names the calling job", run(JOB_STUB.format(group="gh-pages", callee="quarto-publish.yml"),
                                                                WORKFLOW.format(conc=JOB_GH)), 1, "job 'publish' concurrency group")
    expect("job-level caller group that differs passes", run(JOB_STUB.format(group="publish-lock", callee="quarto-publish.yml"),
                                                              WORKFLOW.format(conc=JOB_GH)), 0)
    # The negative that pins "only the CALLING job's own group": a matching
    # group on a sibling job serializes those jobs and never waits on the
    # callee, so reporting it would be a false positive. Widening the check to
    # every job in the stub turns this red.
    expect("group on a non-calling job passes", run(OTHER_JOB_STUB.format(group="gh-pages", callee="quarto-publish.yml"),
                                                     WORKFLOW.format(conc=JOB_GH)), 0)
    # gha#811 review, finding 3: the summary counts calls actually COMPARED, so
    # a call with no caller-level group at all reports zero rather than one.
    expect("a call with no caller group compares zero", run(STUB.format(top="", callee="quarto-publish.yml"),
                                                             WORKFLOW.format(conc=JOB_GH)), 0, "compared 0 reusable-workflow")
    expect("a call with a caller group compares one", run(STUB.format(top="concurrency:\n  group: publish-lock", callee="quarto-publish.yml"),
                                                           WORKFLOW.format(conc=JOB_GH)), 0, "compared 1 reusable-workflow")
    expect("stub count is reported", run(STUB.format(top="", callee="quarto-publish.yml"),
                                          WORKFLOW.format(conc=JOB_GH)), 0, "examined 1 stub(s)")

    if failures:
        print(f"::error::{failures} audit-example-concurrency case(s) failed")
        return 1
    print("All audit-example-concurrency cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
