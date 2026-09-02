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
    expect("missing callee is an error", run(STUB.format(top=TOP_GH, callee="quarto-publish.yml"), None), 2, "not in")
    expect("empty examples dir is an error", run(None, WORKFLOW.format(conc=JOB_GH)), 2, "no example stubs")
    expect("unparsable stub is an error", run("jobs: [\n", WORKFLOW.format(conc=JOB_GH)), 2, "examples/quarto-publish.yml")
    expect("stub with no jobs mapping is an error", run("name: X\non: push\n", WORKFLOW.format(conc=JOB_GH)), 2, "no 'jobs' mapping")
    expect("examined count is reported", run(STUB.format(top="", callee="quarto-publish.yml"),
                                              WORKFLOW.format(conc=JOB_GH)), 0, "examined 1 stub(s) against 1")

    if failures:
        print(f"::error::{failures} audit-example-concurrency case(s) failed")
        return 1
    print("All audit-example-concurrency cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
