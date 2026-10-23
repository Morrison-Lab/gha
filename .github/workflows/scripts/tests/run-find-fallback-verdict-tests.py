#!/usr/bin/env python3
"""Pin find-fallback-verdict.py and the require-clean-verdict wiring (gha#1163).

When the Claude review cannot run (quota exhausted), `require-clean-verdict`
passes only if a clean separate-agent review of the CURRENT head is recorded
as a PR comment from an owner, member or collaborator. gha#1019 requires that
a quota skip with nothing recorded still fails, so each case below is a way
the gate could wrongly go green, plus the one way it should.

Usage::

    python3 run-find-fallback-verdict-tests.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent.parent.parent
FINDER = SCRIPTS / "find-fallback-verdict.py"
CLASSIFIER = SCRIPTS / "classify-review-verdict.sh"
WORKFLOW = REPO / ".github" / "workflows" / "claude-code-review.yml"

HEAD = "a" * 40
OLD = "b" * 40
MARKER = "_Posted by Claude Code (AI agent) --- not written by a human._"
CLEAN = "### Verdict: Ready for merge"
NOT_CLEAN = "### Verdict: Not ready"


def review(verdict=CLEAN, sha=HEAD, marker=True):
    parts = ["Summary: fine.", verdict, f"Reviewed-Commit: {sha}"]
    if marker:
        parts += ["---", MARKER]
    return "\n\n".join(parts)


def comment(body, association="MEMBER", created="2026-10-22T20:00:00Z"):
    return {
        "body": body,
        "author_association": association,
        "created_at": created,
        "html_url": f"https://example.test/c/{created}",
    }


def run_finder(comments):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "comments.json"
        path.write_text(json.dumps(comments))
        result = subprocess.run(
            [sys.executable, str(FINDER), str(path), HEAD, str(CLASSIFIER)],
            capture_output=True,
            text=True,
            check=True,
        )
    return dict(line.split("=", 1) for line in result.stdout.splitlines())


CASES = [
    ("matching clean review from a member", [comment(review())], True),
    ("collaborator counts", [comment(review(), "COLLABORATOR")], True),
    ("owner counts", [comment(review(), "OWNER")], True),
    ("no comments", [], False),
    ("review of an older sha", [comment(review(sha=OLD))], False),
    ("non-member author", [comment(review(), "NONE")], False),
    ("contributor author", [comment(review(), "CONTRIBUTOR")], False),
    ("no agent marker", [comment(review(marker=False))], False),
    ("not-clean verdict", [comment(review(verdict=NOT_CLEAN))], False),
    ("no Reviewed-Commit line", [comment(f"{CLEAN}\n\n{MARKER}")], False),
    (
        "stale review plus a current clean one",
        [comment(review(sha=OLD), created="2026-10-22T21:00:00Z"), comment(review())],
        True,
    ),
    (
        "a newer not-clean review of the same head withdraws a clean one",
        [comment(review(verdict=NOT_CLEAN), created="2026-10-22T21:00:00Z"), comment(review())],
        False,
    ),
    (
        "a newer not-clean review of an older sha does not withdraw a clean one",
        [comment(review(verdict=NOT_CLEAN, sha=OLD), created="2026-10-22T21:00:00Z"), comment(review())],
        True,
    ),
    (
        "a newer not-clean review from a non-member does not withdraw a clean one",
        [comment(review(verdict=NOT_CLEAN), "NONE", created="2026-10-22T21:00:00Z"), comment(review())],
        True,
    ),
    (
        "the PR author's own marked review counts (trust model, gha#1182)",
        [dict(comment(review()), user={"login": "pr-author"})],
        True,
    ),
    (
        "a Reviewed-Commit line inside a code fence does not count",
        [comment(f"Summary.\n\n{CLEAN}\n\n```\nReviewed-Commit: {HEAD}\n```\n\n{MARKER}")],
        False,
    ),
    (
        "a Reviewed-Commit line inside a tilde fence does not count",
        [comment(f"Summary.\n\n{CLEAN}\n\n~~~\nReviewed-Commit: {HEAD}\n~~~\n\n{MARKER}")],
        False,
    ),
    (
        "a blockquoted Reviewed-Commit line does not count",
        [comment(f"{CLEAN}\n\n> Reviewed-Commit: {HEAD}\n\n{MARKER}")],
        False,
    ),
    (
        "an indented-code Reviewed-Commit line does not count",
        [comment(f"{CLEAN}\n\nQuoted:\n\n    Reviewed-Commit: {HEAD}\n\n{MARKER}")],
        False,
    ),
    (
        "a marker inside a code fence does not count",
        [comment(f"{CLEAN}\n\nReviewed-Commit: {HEAD}\n\n```\n{MARKER}\n```")],
        False,
    ),
    (
        "a fence that closes lets later prose count again",
        [comment(f"```\nquoted\n```\n\n{review()}")],
        True,
    ),
    (
        "a shorter closing run does not end a longer fence",
        [comment(f"````\n```\nReviewed-Commit: {HEAD}\n````\n\n{CLEAN}\n\n{MARKER}")],
        False,
    ),
]


def check_wiring():
    """The quota branch must consult the fallback and still fail on a miss."""
    text = WORKFLOW.read_text()
    job = text[text.index("\n  require-clean-verdict:"):]
    finder = text[text.index("\n  find-fallback-verdict:"):text.index("\n  require-clean-verdict:")]
    problems = []
    if "permissions: {}" not in job.split("steps:")[0]:
        problems.append("require-clean-verdict must keep `permissions: {}` (widening breaks callers)")
    if "pull-requests: read" not in finder.split("steps:")[0]:
        problems.append("find-fallback-verdict lacks `pull-requests: read`")
    if "find-fallback-verdict@" not in finder:
        problems.append("find-fallback-verdict job does not use the action")
    if "find-fallback-verdict" not in job.split("steps:")[0]:
        problems.append("require-clean-verdict does not need find-fallback-verdict")
    quota = re.search(r'if \[\[ "\$QUOTA_EXHAUSTED" == "true" \]\]; then(.*?)\n          fi\n', job, re.S)
    if not quota:
        problems.append("quota branch not found")
    else:
        branch = quota.group(1)
        if 'FALLBACK_FOUND" == "true"' not in branch:
            problems.append("quota branch does not test FALLBACK_FOUND")
        if "exit 1" not in branch:
            problems.append("quota branch no longer fails when nothing is recorded (gha#1019)")
    return problems


def main():
    failures = 0
    for name, comments, expected in CASES:
        found = run_finder(comments)["found"] == "true"
        status = "ok" if found == expected else "FAIL"
        if found != expected:
            failures += 1
        print(f"{status}: {name} (found={found}, expected={expected})")
    for problem in check_wiring():
        failures += 1
        print(f"FAIL: wiring: {problem}")
    print(f"{len(CASES)} finder cases, {failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
