#!/usr/bin/env python3
"""Offline cases for audit_example_concurrency.py (gha#809, gha#821).

Each case builds a throwaway examples/ and workflows/ pair, so the cases can
name a collision this repo's own tree must never carry. The negative cases
are the ones to keep if the suite is trimmed: a stub with no top-level block,
a stub whose group differs from the job's, and a callee with no job-level
group must all pass, or the audit would fail every stub the moment any
workflow gained a concurrency block.

The gha#821 cases put a CALLER in the workflows/ directory rather than in
examples/, which is what this repo's own dogfood callers look like. The
top-level collision case is the one to keep from that group: narrowing the
population back to examples/ alone leaves every OLDER case green, because
every older case's collision lives in a stub. The other gha#821 cases do go
red under that mutation too, so the group is not one case wide; what the
top-level case buys is that the group cannot be trimmed away entirely.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "audit_example_concurrency.py"
REPO = SCRIPT.parent.parent.parent.parent
WORKFLOWS = REPO / ".github" / "workflows"

sys.path.insert(0, str(SCRIPT.parent))

from workflow_discovery import is_workflows_restored  # noqa: E402

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


# A callee whose concurrency sits at ITS top level rather than on a job. This
# is the shape `.github/workflows/bump-dev-version.yml` really has, and a
# reusable workflow's top-level group applies to the calling job, so it
# deadlocks a matching caller group exactly as a job-level one does.
CALLEE_TOP = """name: Y
on: workflow_call
concurrency:
  group: {group}
  cancel-in-progress: false
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo build
"""


def run(stub: str | None, workflow: str | None, callee: str = "quarto-publish.yml",
        stub_name: str = "quarto-publish.yml", caller: str | None = None,
        caller_name: str = "website-publish.yml", env: dict[str, str] | None = None):
    """Run the audit over a throwaway tree.

    ``caller`` is written into the WORKFLOWS directory rather than examples/,
    which is where this repo's own dogfood callers live (gha#821).
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        ex = root / "examples"
        wf = root / "workflows"
        ex.mkdir()
        wf.mkdir()
        if stub is not None:
            (ex / stub_name).write_text(stub)
        if workflow is not None:
            (wf / callee).write_text(workflow)
        if caller is not None:
            (wf / caller_name).write_text(caller)
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--examples", str(ex), "--workflows", str(wf)],
            capture_output=True,
            text=True,
            env={**os.environ, "GHA_WORKFLOWS_RESTORED": "", **(env or {})},
        )


def run_live():
    """Run the audit over this repository's own tree (gha#821).

    The environment is inherited, unlike ``run``'s: a fixture tree is never
    restored, so those cases clear the flag to keep an exported one from
    skipping them, but here the flag means what it says. Clearing it would
    fabricate a non-restored run for the one call that reads the real tree,
    and would make the caller's own restore guard unreachable by that route
    -- so the guard would look load-bearing while a mutation of it changed
    nothing (gha#854 review).
    """
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--examples", str(REPO / "examples"),
         "--workflows", str(WORKFLOWS)],
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
    # The case above exercises the STRING form, where `block` is a str. The
    # mapping form strips separately, and without this case that strip can be
    # deleted with the suite green -- a whitespace-only mapping group would
    # then compare as a real name and the stub would pass (gha#811 review,
    # round 4).
    expect("empty group in mapping form is an error", run(STUB.format(top="concurrency:\n  group: '   '", callee="quarto-publish.yml"),
                                                           WORKFLOW.format(conc=JOB_GH)), 2, "names no group")
    # A non-scalar group is refused rather than stringified (Copilot on
    # gha#811 round 2): str([a, b]) is a name nothing can collide with, so the
    # stub would pass the very audit meant to refuse what it cannot evaluate.
    expect("list group is an error", run(STUB.format(top="concurrency:\n  group: [a, b]", callee="quarto-publish.yml"),
                                          WORKFLOW.format(conc=JOB_GH)), 2, "expected a scalar")
    expect("mapping group is an error", run(STUB.format(top="concurrency:\n  group: {}", callee="quarto-publish.yml"),
                                             WORKFLOW.format(conc=JOB_GH)), 2, "expected a scalar")
    # Every non-string scalar is refused. YAML resolution is lossy, so the
    # audit cannot recover the source spelling: 010 arrives as 8, 1:30 as 90.
    # Measured against yaml.safe_load (gha#811 review, round 2).
    for spelling in ["2026", "010", "0x10", "1_000", "+5", "1:30", "true", "1.10", "2026-01-01"]:
        expect(f"unquoted group {spelling!r} is an error",
               run(STUB.format(top=f"concurrency:\n  group: {spelling}", callee="quarto-publish.yml"),
                   WORKFLOW.format(conc=JOB_GH)), 2, "quote it")
    # ...and the quoted form of the same value is accepted and compared.
    expect("a quoted numeric group is compared", run(STUB.format(top="concurrency:\n  group: '2026'", callee="quarto-publish.yml"),
                                                      WORKFLOW.format(conc="    concurrency:\n      group: '2026'")), 1, "deadlock")
    # The third fail-closed guard in the parsing path: a concurrency block that
    # is neither a string nor a mapping. It had no case and survived mutation
    # to `return None`, which would report a stub the audit never evaluated as
    # clean (gha#811 review, round 2).
    expect("a list concurrency block is an error", run(STUB.format(top="concurrency: [gh-pages]", callee="quarto-publish.yml"),
                                                        WORKFLOW.format(conc=JOB_GH)), 2, "expected a string or mapping")
    # A workflow the stub does not name, so the workflows dir is non-empty
    # and the callee is the only missing thing; an empty dir is refused by
    # its own guard below (gha#854 review, finding 2).
    expect("missing callee is an error", run(STUB.format(top=TOP_GH, callee="quarto-publish.yml"),
                                              WORKFLOW.format(conc=JOB_GH), callee="unrelated.yml"), 2, "not in")
    expect("empty workflows dir is an error", run(STUB.format(top=TOP_GH, callee="quarto-publish.yml"),
                                                   None), 2, "no workflow files found")
    expect("empty examples dir is an error", run(None, WORKFLOW.format(conc=JOB_GH)), 2, "no example stubs")
    # A distinct caller filename, because the needle can no longer carry the
    # directory -- `examples/` renders with a backslash on Windows -- and the
    # stub and the callee otherwise default to the same name (gha#854
    # review, finding 8).
    expect("unparsable stub is an error", run("jobs: [\n", WORKFLOW.format(conc=JOB_GH),
                                               stub_name="broken-stub.yml"), 2, "broken-stub.yml: ")
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
                                                             WORKFLOW.format(conc=JOB_GH)), 0, "compared 0 of them")
    expect("a call with a caller group compares one", run(STUB.format(top="concurrency:\n  group: publish-lock", callee="quarto-publish.yml"),
                                                           WORKFLOW.format(conc=JOB_GH)), 0, "compared 1 of them")
    # The callee in workflows/ is a candidate caller too (it calls nothing), so
    # the population here is two files: one stub, one workflow.
    expect("population count names both roots", run(STUB.format(top="", callee="quarto-publish.yml"),
                                                    WORKFLOW.format(conc=JOB_GH)), 0, "examined 2 workflow file(s) (1 under")

    # gha#811 review: the CALLEE side has two placements too. Checking only its
    # jobs missed a workflow_call workflow carrying its own top-level group.
    expect("callee top-level group collides", run(STUB.format(top=TOP_GH, callee="quarto-publish.yml"),
                                                   CALLEE_TOP.format(group="gh-pages")), 1, "its top level")
    expect("callee top-level group that differs passes", run(STUB.format(top=TOP_GH, callee="quarto-publish.yml"),
                                                              CALLEE_TOP.format(group="bump-dev-version")), 0)
    # The population includes *.yaml, which no other case and no live run can
    # pin -- this repo's examples/ holds only *.yml, so reverting the glob to
    # *.yml alone leaves every other case and the live audit green. Verbatim
    # the class CLAUDE.md documents for workflow_discovery.
    expect("a .yaml stub is in the population", run(STUB.format(top=TOP_GH, callee="quarto-publish.yml"),
                                                     WORKFLOW.format(conc=JOB_GH),
                                                     stub_name="quarto-publish.yaml"), 1, "deadlock")
    # Fail-closed guards. Each refuses rather than walking past, so a malformed
    # stub cannot be reported as clean; without these cases each `die` can be
    # replaced by `continue` with the suite still green.
    expect("a non-mapping job is an error", run("name: X\non: push\njobs:\n  publish: 7\n",
                                                 WORKFLOW.format(conc=JOB_GH)), 2, "expected a mapping")
    expect("a non-string uses: is an error", run("name: X\non: push\njobs:\n  publish:\n    uses: [a]\n",
                                                  WORKFLOW.format(conc=JOB_GH)), 2, "expected a string")
    # The owner anchor is deliberate: a `uses:` naming somebody else's repo is
    # not ours to audit, and is skipped rather than resolved against our
    # workflows dir. Loosening USES_RE to any owner turns this red with exit 1
    # -- the fixture's callee IS present under that name, so the loosened
    # regex resolves it and reports a real `gh-pages` collision (measured;
    # an earlier version of this comment said exit 2 on a missing file).
    expect("another owner's uses: is skipped", run("name: X\non: push\n" + TOP_GH + "\njobs:\n  publish:\n    uses: someone-else/gha/.github/workflows/quarto-publish.yml@v2\n",
                                                    WORKFLOW.format(conc=JOB_GH)), 0, "compared 0")

    # gha#821: callers are derived from the `uses:` edge, so a caller living in
    # the workflows directory -- this repo's own dogfood shape -- is in the
    # population. The stub here carries no group, so the only collision is the
    # dogfood caller's; narrowing the population back to examples/ alone turns
    # this red with exit 0.
    expect("a collision in a caller outside examples/ is reported",
           run(STUB.format(top="", callee="quarto-publish.yml"), WORKFLOW.format(conc=JOB_GH),
               caller=STUB.format(top=TOP_GH, callee="quarto-publish.yml")), 1, "website-publish.yml: top-level")
    # The job-level placement in a dogfood caller, so the gha#811 job-level
    # check is not silently examples-only.
    expect("a job-level collision in a caller outside examples/ is reported",
           run(STUB.format(top="", callee="quarto-publish.yml"), WORKFLOW.format(conc=JOB_GH),
               caller=JOB_STUB.format(group="gh-pages", callee="quarto-publish.yml")), 1, "website-publish.yml: job 'publish'")
    expect("a caller outside examples/ with a different group passes",
           run(STUB.format(top="", callee="quarto-publish.yml"), WORKFLOW.format(conc=JOB_GH),
               caller=STUB.format(top="concurrency:\n  group: website-publish-${{ github.ref }}", callee="quarto-publish.yml")), 0)
    # The workflows-root half of the population is discovered through
    # workflow_discovery, so it carries *.yaml too. examples/ and
    # .github/workflows/ both hold only *.yml, so a *.yml-only listing on the
    # workflows side leaves every other case and the live run green.
    expect("a .yaml caller outside examples/ is in the population",
           run(STUB.format(top="", callee="quarto-publish.yml"), WORKFLOW.format(conc=JOB_GH),
               caller=STUB.format(top=TOP_GH, callee="quarto-publish.yml"),
               caller_name="website-publish.yaml"), 1, "website-publish.yaml: top-level")
    # workflow_discovery excludes dotfiles, because GitHub never loads them; a
    # `.restored-from-default-branch` marker or an editor's dotfile must not
    # be parsed as a caller. Listing every file turns this red with exit 2.
    expect("a dotfile in the workflows directory is not a caller",
           run(STUB.format(top="", callee="quarto-publish.yml"), WORKFLOW.format(conc=JOB_GH),
               caller="not yaml: [\n", caller_name=".editor-scratch.yml"), 0)
    # The examined count names both roots and the calls found, so a population
    # that shrank back to the stubs alone reads differently. The dogfood caller
    # and the stub each call the callee once, and the callee itself calls
    # nothing.
    expect("the examined count includes the workflows-root callers",
           run(STUB.format(top="", callee="quarto-publish.yml"), WORKFLOW.format(conc=JOB_GH),
               caller=STUB.format(top="", callee="quarto-publish.yml")), 0,
           "examined 3 workflow file(s) (1 under")
    expect("the call count includes the workflows-root callers",
           run(STUB.format(top="", callee="quarto-publish.yml"), WORKFLOW.format(conc=JOB_GH),
               caller=STUB.format(top="", callee="quarto-publish.yml")), 0,
           "found 2 call(s)")
    # Under a default-branch restore the files on disk are not the PR's, so the
    # audit skips with a notice like every sibling audit (gha#598, gha#765).
    # The fixture collides, so dropping the skip turns this red with exit 1.
    expect("a restored workflows tree skips with a notice",
           run(STUB.format(top=TOP_GH, callee="quarto-publish.yml"), WORKFLOW.format(conc=JOB_GH),
               env={"GHA_WORKFLOWS_RESTORED": "1"}), 0, "::notice::Skipping audit-example-concurrency")

    # The live tree: the audit still passes, and its population counts the
    # dogfood callers under .github/workflows/ alongside the examples/ stubs.
    # The counts are derived from the tree rather than written here, so a new
    # stub or workflow does not turn this case red.
    # Deliberately NOT workflow_discovery.discover_workflows, which is what
    # the audit itself walks: an expected value computed by the code under
    # test agrees with it by construction, so a narrowed glob would move both
    # sides together and leave this green. The duplication is the negative
    # control (gha#854 review, finding 7).
    def listing(root: pathlib.Path) -> list[pathlib.Path]:
        return [p for p in root.iterdir()
                if p.is_file() and p.suffix in (".yml", ".yaml") and not p.name.startswith(".")]

    stub_files = listing(REPO / "examples")
    stubs = len(stub_files)
    dogfood = listing(WORKFLOWS)
    # Only the LIVE block is skipped under a default-branch restore, where the
    # sibling suites skip outright: every case above builds its own throwaway
    # tree and is unaffected by what is on disk here. The files under
    # WORKFLOWS are then the default branch's callers rather than this PR's,
    # so a count derived from them says nothing about the diff -- and the
    # audit itself would skip, leaving no summary for these assertions to read
    # (gha#598, gha#765; gha#854 review, finding 1).
    if is_workflows_restored(WORKFLOWS):
        print("SKIP live-tree cases: .github/workflows/ was restored from the "
              "default branch (gha#598, gha#765)")
        if failures:
            print(f"::error::{failures} audit-example-concurrency case(s) failed")
            return 1
        print("All audit-example-concurrency cases passed.")
        return 0

    live = run_live()
    expect("the live tree passes", live, 0)
    expect("the live population counts both roots",
           live, 0, f"examined {stubs + len(dogfood)} workflow file(s) ({stubs} under")
    # A textual floor for the call count: every `uses: Morrison-Lab/gha/...`
    # line under .github/workflows/ is a dogfood call the parsed walk must
    # also find. Zero dogfood calls would make the assertion vacuous, so that
    # is a failure too.
    found = re.search(r"found (\d+) call\(s\)", live.stdout)
    def textual_calls(paths: list[pathlib.Path]) -> int:
        return sum(
            1 for p in paths
            for line in p.read_text(encoding="utf-8").splitlines()
            if line.lstrip().startswith("uses: Morrison-Lab/gha/.github/workflows/")
        )

    dogfood_calls = textual_calls(dogfood)
    # The floor is BOTH roots' calls, not the dogfood ones alone. The summary
    # reports one total across both, and the stubs alone contribute several
    # times what the dogfood callers do -- so a floor of `dogfood_calls` is
    # cleared by the stubs by themselves, and stays cleared after the dogfood
    # callers are dropped from the population entirely. That assertion could
    # not go red (gha#854 review, finding 3).
    floor = textual_calls(stub_files) + dogfood_calls
    if found is None or dogfood_calls == 0 or int(found.group(1)) < floor:
        print(f"::error::the live call count must be at least {floor} "
              f"({dogfood_calls} of them dogfood call(s)); "
              f"summary was {live.stdout!r}")
        failures += 1
    else:
        print("OK   the live call count includes the dogfood callers")

    if failures:
        print(f"::error::{failures} audit-example-concurrency case(s) failed")
        return 1
    print("All audit-example-concurrency cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
