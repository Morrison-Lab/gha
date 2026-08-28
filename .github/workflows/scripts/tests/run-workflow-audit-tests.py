#!/usr/bin/env python3
"""Offline tests for the two workflow audits `_selftest.yml` runs (gha#716).

These cover the AUDITS, not just the discovery underneath them, and that
distinction is the point: this repo's real tree carries 63 ``.yml`` workflows
and zero ``.yaml`` ones, so a consumer reverted to a ``*.yml``-only glob would
leave every other check green.  Each audit therefore gets a fixture whose
violation lives in a ``.yaml`` file, which no yml-only discovery can see.

The other cases to keep if this is ever trimmed are the negative ones, because
each pins a decision that is silent when reversed: an unparsable file is an
error rather than a clean file, an empty directory is an error rather than an
empty list, ``submodules-token:`` is not ``token:``, and a nested
``scripts/foo.yml`` is not a workflow.

Usage::

    python3 run-workflow-audit-tests.py
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import audit_workflow_action_pins as pins  # noqa: E402
import audit_workflow_token_usage as token  # noqa: E402
from workflow_discovery import discover_workflows  # noqa: E402

# Assembled rather than typed, so this fixture text cannot itself be mistaken
# for a real expression by anything scanning this repo.
EXPR = "$" + "{{"

PINNED = "actions/checkout@1111111111111111111111111111111111111111"

failures = 0
cases = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global failures, cases
    cases += 1
    if condition:
        print(f"OK   {label}")
    else:
        print(f"::error::{label}{': ' + detail if detail else ''}", file=sys.stderr)
        failures += 1


def write(root: pathlib.Path, name: str, body: str) -> pathlib.Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def audit(module, directory: pathlib.Path) -> int:
    """Run one audit, swallowing its own output.

    An expected failure still prints `::error::`, and GitHub renders every one
    of those as an annotation --- so an unmuted suite decorates a passing job
    with a dozen errors it deliberately provoked, which is worse than useless
    to whoever reads the run.
    """
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        return module.main(["--workflows-dir", str(directory)])


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        # ------------------------------------------------------ discovery
        disc = root / "discovery"
        write(disc, "a.yml", "name: a\n")
        write(disc, "b.yaml", "name: b\n")
        write(disc, "c.txt", "not a workflow\n")
        write(disc, "scripts/nested.yml", "name: nested\n")
        check(
            "discovery: both extensions, no .txt, no nested file",
            [p.name for p in discover_workflows(disc)] == ["a.yml", "b.yaml"],
            f"got {[p.name for p in discover_workflows(disc)]}",
        )

        # ----------------------------------------------------- token audit
        clean = root / "token-clean"
        write(
            clean,
            "a.yml",
            "jobs:\n"
            "  run:\n"
            "    steps:\n"
            "      - name: checkout\n"
            f"        uses: {PINNED}\n"
            "        with:\n"
            f"          submodules-token: {EXPR} secrets.SUBMODULES_TOKEN }}}}\n",
        )
        check(
            "token: submodules-token: is not flagged",
            audit(token, clean) == 0,
        )

        for ext in ("yml", "yaml"):
            bad = root / f"token-bad-{ext}"
            write(
                bad,
                f"a.{ext}",
                "jobs:\n"
                "  run:\n"
                "    steps:\n"
                "      - name: checkout\n"
                f"        uses: {PINNED}\n"
                "        with:\n"
                f"          token: {EXPR} secrets.SUBMODULES_TOKEN }}}}\n",
            )
            check(
                f"token: a .{ext} violation fails",
                audit(token, bad) == 1,
            )

        # ------------------------------------------------------ pins audit
        pins_clean = root / "pins-clean"
        write(
            pins_clean,
            "a.yml",
            "jobs:\n"
            "  call:\n"
            "    uses: Morrison-Lab/gha/.github/workflows/spellcheck.yml@v2\n"
            "  run:\n"
            "    steps:\n"
            f"      - uses: {PINNED}\n"
            "      - name: local\n"
            "        uses: ./.github/actions/local-thing\n",
        )
        check(
            "pins: pinned, local and self refs pass",
            audit(pins, pins_clean) == 0,
        )

        # gha#720: BOTH spellings must be caught. The list-item form is the one
        # the line-anchored regex this audit replaced could never see, so it is
        # first here rather than an afterthought.
        for label, step_block in (
            ("list-item form", f"      - uses: actions/checkout@v4\n"),
            (
                "continuation form",
                "      - name: checkout\n        uses: actions/checkout@v4\n",
            ),
        ):
            for ext in ("yml", "yaml"):
                bad = root / f"pins-{label.replace(' ', '-')}-{ext}"
                write(
                    bad,
                    f"a.{ext}",
                    "jobs:\n  run:\n    steps:\n" + step_block,
                )
                check(
                    f"pins: an unpinned {label} in a .{ext} file fails",
                    audit(pins, bad) == 1,
                )

        job_uses = root / "pins-job-uses"
        write(
            job_uses,
            "a.yml",
            "jobs:\n  call:\n    uses: someone/else/.github/workflows/x.yml@main\n",
        )
        check(
            "pins: an unpinned reusable-workflow call fails",
            audit(pins, job_uses) == 1,
        )

        # A `uses:` inside a run: block is text, not a reference. This is what
        # made widening the old regex the wrong fix (gha#720).
        heredoc = root / "pins-heredoc"
        write(
            heredoc,
            "a.yml",
            "jobs:\n"
            "  run:\n"
            "    steps:\n"
            "      - run: |\n"
            "          cat > bad.yml <<EOF\n"
            "          steps:\n"
            "            - uses: actions/checkout@v4\n"
            "          EOF\n",
        )
        check(
            "pins: a uses: written inside a run: block is not a reference",
            audit(pins, heredoc) == 0,
        )

        # ------------------------------------- refusals, not silent passes
        for name, module in (("token", token), ("pins", pins)):
            unparsable = root / f"{name}-unparsable"
            write(unparsable, "a.yml", "jobs:\n  run:\n   - bad\n  : : :\n")
            check(
                f"{name}: an unparsable workflow is an error, not a clean file",
                audit(module, unparsable) == 2,
            )

            empty = root / f"{name}-empty"
            empty.mkdir(parents=True, exist_ok=True)
            check(
                f"{name}: an empty workflows directory fails closed",
                audit(module, empty) == 2,
            )

            check(
                f"{name}: a missing workflows directory fails closed",
                audit(module, root / f"{name}-absent") == 2,
            )

    if failures:
        print(f"::error::{failures} of {cases} workflow-audit case(s) failed", file=sys.stderr)
        return 1
    print(f"All {cases} workflow-audit tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
