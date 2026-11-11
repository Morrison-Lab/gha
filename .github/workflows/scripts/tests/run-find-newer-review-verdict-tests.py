#!/usr/bin/env python3
"""Pin find-newer-review-verdict.py (gha#1365).

An older review run whose verdict was not clean may defer to a newer run's
clean review of the same head, and to nothing else. Each case below is a way
the gate could wrongly go green, plus the ways it should.

Usage::

    python3 run-find-newer-review-verdict-tests.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
FINDER = SCRIPTS / "find-newer-review-verdict.py"
CLASSIFIER = SCRIPTS / "classify-review-verdict.sh"

HEAD = "a" * 40
OLD = "b" * 40
RUN = 100
CLEAN = "### Verdict\n\n**Ready for merge.**"
NOT_CLEAN = "### Verdict\n\n**Needs more work.**"


def posted(verdict=CLEAN, sha=HEAD, run=RUN + 1, login="github-actions[bot]"):
    body = (
        f"**Claude finished review** — [View run](https://github.com/o/r/actions/runs/{run})"
        f"\n\n---\n\nSummary: fine.\n\n{verdict}\n\nReviewed commit: {sha}"
    )
    return {"body": body, "user": {"login": login}, "html_url": f"https://example.test/c/{run}"}


def run_finder(comments, run_id=RUN, classifier=CLASSIFIER):
    """Run the finder and return (outputs, stderr)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "comments.json"
        path.write_text(json.dumps(comments))
        result = subprocess.run(
            [sys.executable, str(FINDER), str(path), HEAD, str(run_id), str(classifier)],
            capture_output=True,
            text=True,
            check=True,
        )
    return dict(line.split("=", 1) for line in result.stdout.splitlines()), result.stderr


CASES = [
    ("a newer clean review of the head counts", [posted()], True),
    ("no comments", [], False),
    ("only this run's own review", [posted(verdict=NOT_CLEAN, run=RUN)], False),
    ("an older clean review does not count", [posted(run=RUN - 1)], False),
    ("a newer clean review of another sha does not count", [posted(sha=OLD)], False),
    ("a newer not-clean review does not count", [posted(verdict=NOT_CLEAN)], False),
    (
        "the newest review decides: a not-clean one after a clean one",
        [posted(run=RUN + 1), posted(verdict=NOT_CLEAN, run=RUN + 2)],
        False,
    ),
    (
        "the newest review decides: a clean one after a not-clean one",
        [posted(verdict=NOT_CLEAN, run=RUN + 1), posted(run=RUN + 2)],
        True,
    ),
    ("a review posted by another account does not count", [posted(login="someone")], False),
    (
        "a stamp that is not the last line does not count",
        [dict(posted(sha=OLD), body=posted(sha=OLD)["body"] + f"\n\nReviewed commit: {HEAD} quoted")],
        False,
    ),
    (
        "a quoted stamp above the real one does not count",
        [dict(posted(sha=OLD), body=posted(sha=OLD)["body"].replace("Summary: fine.", f"Reviewed commit: {HEAD}"))],
        False,
    ),
    (
        "a body without the header does not count",
        [dict(posted(), body=posted()["body"].replace("**Claude finished review**", "Claude finished"))],
        False,
    ),
]


def check_ordering_is_numeric():
    """Run ids compare as numbers, so run 99 is older than run 100."""
    outputs, _ = run_finder([posted(run=99)], run_id=100)
    return [] if outputs["found"] == "false" else ["run 99 was read as newer than run 100"]


def check_classifier_failure():
    """A classifier failure on the newest review counts as not clean."""
    with tempfile.TemporaryDirectory() as tmp:
        failing = Path(tmp) / "failing.sh"
        failing.write_text("#!/usr/bin/env bash\nexit 7\n")
        outputs, stderr = run_finder([posted()], classifier=failing)
    problems = []
    if outputs["found"] != "false":
        problems.append("a classifier failure counted as clean")
    if "classifier exited 7" not in stderr:
        problems.append("the classifier failure is not logged")
    return problems


def main():
    failures = 0
    for name, comments, expected in CASES:
        found = run_finder(comments)[0]["found"] == "true"
        if found != expected:
            failures += 1
        print(f"{'ok' if found == expected else 'FAIL'}: {name} (found={found}, expected={expected})")
    for problem in check_ordering_is_numeric() + check_classifier_failure():
        failures += 1
        print(f"FAIL: {problem}")
    print(f"{len(CASES)} finder cases, {failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
