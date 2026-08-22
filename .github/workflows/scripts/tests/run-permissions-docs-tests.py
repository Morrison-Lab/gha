#!/usr/bin/env python3
"""Assert the prose lists of read-only capabilities agree with the workflows.

The same fact -- which reusable workflows need only the default
``contents: read``, so a caller needs no ``permissions:`` block -- is stated in
``README.md`` and again in ``website/permissions.qmd``.  Nothing derived one
from the other, so they drifted: at the time gha#559 was filed README named
seven and the website named three, while the workflows themselves said
eighteen.

The authoritative source is each reusable workflow's own ``permissions:``
blocks, which is what this script reads.  A workflow is read-only when every
permission it declares -- at workflow level or on any job -- is ``read`` or
``none``.

Each doc marks its list with HTML comments so the extraction is exact rather
than a guess at which bullet is the right one, and so an editor adding a
capability sees that a check is watching::

    - <!--readonly-workflows:begin-->`check-phi`, `lint-yaml`,
      `spellcheck`<!--readonly-workflows:end--> need only `contents: read` ...

**What it does not cover.** It checks the marked list, and nothing outside it.
A doc can still carry a per-workflow caveat -- "this one also needs
``actions: read`` if you narrow below the default token" -- that its counterpart
omits, and this guard will not see the difference. The review of the PR that
added this script caught exactly that, in the same diff: ``README.md`` gained
such a caveat for ``check-equation-renders`` and ``website/permissions.qmd``
did not. Widening the guard to compare free prose is a much larger job than
comparing a delimited list, so the list is what is mechanized and the caveats
remain a human check.

PyYAML is required. It ships preinstalled on the GitHub-hosted Ubuntu runner
image, which is where ``_selftest.yml`` runs this; the import is guarded so a
runner that ever drops it fails with an actionable message rather than a
traceback.

Usage::

    python3 run-permissions-docs-tests.py [--workflows-dir DIR] [--doc PATH ...]
    python3 run-permissions-docs-tests.py --self-test
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import tempfile

BEGIN = "<!--readonly-workflows:begin-->"
END = "<!--readonly-workflows:end-->"

DEFAULT_WORKFLOWS_DIR = ".github/workflows"
DEFAULT_DOCS = ("README.md", "website/permissions.qmd")

# A permission value that does not require the caller to grant anything beyond
# the read-only default token.
READ_VALUES = {"read", "none"}


def die(message: str) -> None:
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(1)


def load_yaml(path: pathlib.Path):
    # Imported lazily so --help works without PyYAML, and guarded so its
    # absence names the fix instead of surfacing as an ImportError traceback.
    try:
        import yaml
    except ImportError:  # pragma: no cover - depends on the runner image
        die(
            "PyYAML is required to derive permissions from the workflows "
            "(install it with `python3 -m pip install pyyaml`)."
        )

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def declared_permissions(doc) -> list[dict]:
    """Every ``permissions:`` mapping in a workflow, top-level and per-job.

    A scalar form (``permissions: read-all`` / ``write-all``) is normalized to
    a mapping so callers never have to re-handle it.
    """
    found = []

    def add(value):
        if isinstance(value, dict):
            found.append(value)
        elif value == "read-all":
            found.append({"contents": "read"})
        elif value == "write-all":
            found.append({"contents": "write"})

    add(doc.get("permissions"))
    for job in (doc.get("jobs") or {}).values():
        if isinstance(job, dict):
            add(job.get("permissions"))
    return found


def is_reusable(doc) -> bool:
    # PyYAML parses a bare `on:` key as the boolean True, so check both spellings.
    triggers = doc.get(True, doc.get("on"))
    return isinstance(triggers, dict) and "workflow_call" in triggers


def read_only_workflows(workflows_dir: pathlib.Path) -> set[str]:
    read_only, unclassifiable = set(), []

    for path in sorted(workflows_dir.glob("*.yml")):
        doc = load_yaml(path)
        if not isinstance(doc, dict) or not is_reusable(doc):
            continue

        blocks = declared_permissions(doc)
        if not blocks:
            # Silence here would classify the workflow as read-only on no
            # evidence at all, which is the direction that under-reports what a
            # caller must grant. Refuse instead.
            unclassifiable.append(path.name)
            continue

        if all(v in READ_VALUES for block in blocks for v in block.values()):
            read_only.add(path.stem)

    if unclassifiable:
        die(
            "these reusable workflows declare no permissions anywhere, so they "
            "cannot be classified as read-only or not: "
            + ", ".join(unclassifiable)
        )
    return read_only


def documented_workflows(doc_path: pathlib.Path) -> set[str]:
    text = doc_path.read_text(encoding="utf-8")
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        die(
            f"{doc_path}: expected exactly one {BEGIN} ... {END} marker pair "
            f"around the read-only capability list (found {text.count(BEGIN)} "
            f"begin and {text.count(END)} end markers)."
        )

    marked = text.split(BEGIN, 1)[1].split(END, 1)[0]
    names = set(re.findall(r"`([^`]+)`", marked))
    stray = {n for n in names if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", n)}
    if stray:
        die(
            f"{doc_path}: the marked list must contain only backticked "
            "capability names; found " + ", ".join(f"`{s}`" for s in sorted(stray))
        )
    if not names:
        die(f"{doc_path}: the marked read-only capability list is empty.")
    return names


def check(workflows_dir: pathlib.Path, docs: list[pathlib.Path]) -> int:
    expected = read_only_workflows(workflows_dir)
    if not expected:
        die(f"no read-only reusable workflows found under {workflows_dir}.")

    failures = 0
    for doc_path in docs:
        documented = documented_workflows(doc_path)
        missing = sorted(expected - documented)
        extra = sorted(documented - expected)
        if missing or extra:
            failures += 1
            if missing:
                print(
                    f"::error file={doc_path}::read-only capabilities missing from "
                    f"this list: {', '.join(missing)}"
                )
            if extra:
                print(
                    f"::error file={doc_path}::listed as read-only but the "
                    f"workflow declares a write permission (or does not exist): "
                    f"{', '.join(extra)}"
                )
        else:
            print(f"OK   {doc_path} lists all {len(expected)} read-only capabilities")

    if failures:
        print(
            "::error::The read-only capability lists disagree with the "
            "workflows' own permissions blocks. Update the list(s) between the "
            f"{BEGIN} / {END} markers."
        )
    return 1 if failures else 0


# --------------------------------------------------------------------------
# Offline self-test
# --------------------------------------------------------------------------

WORKFLOW_READONLY = """\
on:
  workflow_call:
jobs:
  run:
    permissions:
      contents: read
    steps:
      - run: 'true'
"""

WORKFLOW_WRITER = """\
on:
  workflow_call:
permissions:
  contents: read
jobs:
  run:
    permissions:
      issues: write
    steps:
      - run: 'true'
"""

# Not a reusable workflow, so it must be ignored however it is permissioned.
WORKFLOW_NOT_REUSABLE = """\
on:
  push:
jobs:
  run:
    permissions:
      contents: read
    steps:
      - run: 'true'
"""

WORKFLOW_UNDECLARED = """\
on:
  workflow_call:
jobs:
  run:
    steps:
      - run: 'true'
"""


def run_self_test() -> int:
    script = pathlib.Path(__file__).resolve()

    def run(workflows_dir, docs):
        return subprocess.run(
            [sys.executable, str(script), "--workflows-dir", str(workflows_dir)]
            + [arg for d in docs for arg in ("--doc", str(d))],
            capture_output=True,
            text=True,
        )

    def expect(label, result, should_pass, needle=None):
        passed = result.returncode == 0
        if passed != should_pass:
            print(f"::error::{label}: expected {'pass' if should_pass else 'failure'}, "
                  f"got exit {result.returncode}\n{result.stdout}{result.stderr}",
                  file=sys.stderr)
            return 1
        if needle and needle not in (result.stdout + result.stderr):
            print(f"::error::{label}: expected output to mention {needle!r}\n"
                  f"{result.stdout}{result.stderr}", file=sys.stderr)
            return 1
        print(f"OK   {label}")
        return 0

    print("Running run-permissions-docs-tests offline unit tests...")
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        wf = root / "workflows"
        wf.mkdir()
        (wf / "alpha.yml").write_text(WORKFLOW_READONLY)
        (wf / "beta.yml").write_text(WORKFLOW_READONLY)
        (wf / "gamma.yml").write_text(WORKFLOW_WRITER)
        (wf / "delta.yml").write_text(WORKFLOW_NOT_REUSABLE)

        def doc(name, body):
            p = root / name
            p.write_text(f"prose\n\n- {BEGIN}{body}{END} need only `contents: read`.\n")
            return p

        agreeing = doc("agree.md", "`alpha`, `beta`")

        # 1. Agreement passes.
        failures += expect("agreeing list passes", run(wf, [agreeing]), True)

        # 2. The gha#559 defect itself: a read-only capability missing from the list.
        failures += expect(
            "a missing capability fails",
            run(wf, [doc("missing.md", "`alpha`")]),
            False,
            "missing from this list: beta",
        )

        # 3. The opposite drift: a capability listed that actually writes.
        failures += expect(
            "a write-permissioned capability in the list fails",
            run(wf, [doc("extra.md", "`alpha`, `beta`, `gamma`")]),
            False,
            "declares a write permission",
        )

        # 4. A non-reusable workflow is not part of the expected set, so listing
        #    only the two reusable read-only ones must still pass (guards against
        #    the workflow_call filter being dropped).
        failures += expect("non-reusable workflows are ignored", run(wf, [agreeing]), True)

        # 5. Several docs are all checked, not just the first.
        failures += expect(
            "a second doc's drift is reported",
            run(wf, [agreeing, doc("second.md", "`alpha`")]),
            False,
            "missing from this list: beta",
        )

        # 6. A missing marker pair is an error, not a silent pass.
        unmarked = root / "unmarked.md"
        unmarked.write_text("- `alpha`, `beta` need only `contents: read`.\n")
        failures += expect(
            "an unmarked doc fails", run(wf, [unmarked]), False, "marker pair"
        )

        # 7. Non-name content inside the markers is an error, so a marker
        #    accidentally widened to swallow prose cannot pass vacuously.
        noisy = root / "noisy.md"
        noisy.write_text(f"- {BEGIN}`alpha`, `beta` need only `contents: read`{END}.\n")
        failures += expect(
            "prose inside the markers fails", run(wf, [noisy]), False, "only backticked"
        )

        # 8. A reusable workflow declaring no permissions at all is refused
        #    rather than counted as read-only.
        wf2 = root / "workflows-undeclared"
        wf2.mkdir()
        (wf2 / "alpha.yml").write_text(WORKFLOW_READONLY)
        (wf2 / "omega.yml").write_text(WORKFLOW_UNDECLARED)
        failures += expect(
            "an undeclared workflow is refused",
            run(wf2, [doc("undeclared.md", "`alpha`")]),
            False,
            "cannot be classified",
        )

    if failures:
        print(f"::error::{failures} self-test case(s) failed", file=sys.stderr)
        return 1
    print("All run-permissions-docs-tests self-tests passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows-dir", default=DEFAULT_WORKFLOWS_DIR)
    parser.add_argument("--doc", action="append", dest="docs")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    docs = [pathlib.Path(d) for d in (args.docs or DEFAULT_DOCS)]
    for d in docs:
        if not d.is_file():
            die(f"{d}: no such file")

    workflows_dir = pathlib.Path(args.workflows_dir)
    if not workflows_dir.is_dir():
        die(f"{workflows_dir}: no such directory")

    return check(workflows_dir, docs)


if __name__ == "__main__":
    sys.exit(main())
