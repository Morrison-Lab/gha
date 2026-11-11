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


def run_finder_full(comments, classifier=CLASSIFIER):
    """Run the finder and return (outputs, stderr)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "comments.json"
        path.write_text(json.dumps(comments))
        result = subprocess.run(
            [sys.executable, str(FINDER), str(path), HEAD, str(classifier)],
            capture_output=True,
            text=True,
            check=True,
        )
    outputs = dict(line.split("=", 1) for line in result.stdout.splitlines())
    return outputs, result.stderr


def run_finder(comments):
    return run_finder_full(comments)[0]


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
        "a marker on the second line of an indented code block does not count",
        [comment(f"{CLEAN}\n\nReviewed-Commit: {HEAD}\n\nQuoted:\n\n    first\n    {MARKER}")],
        False,
    ),
    (
        "prose after an indented code block counts again",
        [comment(f"Quoted:\n\n    first\n    second\n\n{review()}")],
        True,
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
        "several Reviewed-Commit lines: the last one names the head (gha#1229)",
        [comment(f"Summary.\n\n{CLEAN}\n\nReviewed-Commit: {OLD}\n\nReviewed-Commit: {HEAD}\n\n{MARKER}")],
        True,
    ),
    (
        "several Reviewed-Commit lines: an earlier one naming the head does not count (gha#1229)",
        [comment(f"Summary.\n\n{CLEAN}\n\nReviewed-Commit: {HEAD}\n\nReviewed-Commit: {OLD}\n\n{MARKER}")],
        False,
    ),
    (
        "the lds#1521 fallback comment shape counts (gha#1288)",
        [comment(f"Separate-agent review.\n\nReviewed-Commit: {HEAD}\n\nVerdict: Clean. No findings.\n\n{MARKER}")],
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
    # gha#1365 gave the gate `pull-requests: read`, which find-fallback-verdict
    # already requests; run-find-newer-review-verdict-tests.py pins that block.
    if "pull-requests: read" not in finder.split("steps:")[0]:
        problems.append("find-fallback-verdict lacks `pull-requests: read`")
    if "find-fallback-verdict@" not in finder:
        problems.append("find-fallback-verdict job does not use the action")
    if "find-fallback-verdict" not in job.split("steps:")[0]:
        problems.append("require-clean-verdict does not need find-fallback-verdict")
    head = finder.split("steps:")[0]
    needs = re.search(r"\n    needs: \[([^\]]*)\]", head)
    if not needs or {"gather-context", "claude-review"} - {n.strip() for n in needs.group(1).split(",")}:
        problems.append("find-fallback-verdict must need gather-context and claude-review (gha#1229)")
    if "fromJSON(needs.claude-review.outputs.quota_exhausted" not in head:
        problems.append("find-fallback-verdict no longer runs only on a quota skip")
    sha = re.search(r"\n          head-sha: (.*)\n", finder)
    expected = "${{ github.event.pull_request.head.sha || needs.gather-context.outputs.stash-head }}"
    if not sha or sha.group(1).strip() != expected:
        problems.append("find-fallback-verdict must match the reviewed commit, not the live head (gha#1229)")
    if "FALLBACK_FOUND: ${{ needs.find-fallback-verdict.outputs.found }}" not in job:
        problems.append("FALLBACK_FOUND must come from find-fallback-verdict's job output")
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


def check_classifier_failure():
    """A classifier failure on the newest review is a miss, not a skip to an older one (gha#1229)."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        flaky = Path(tmp) / "flaky-classifier.sh"
        # Fails on a comment containing CRASH, and delegates to the real classifier otherwise.
        flaky.write_text(f'#!/usr/bin/env bash\nif grep -q CRASH "$1"; then exit 7; fi\nexec bash "{CLASSIFIER}" "$@"\n')
        crashing = comment(review().replace("Summary: fine.", "Summary: CRASH."), created="2026-10-22T21:00:00Z")
        outputs, stderr = run_finder_full([crashing, comment(review())], flaky)
    if outputs.get("found") != "false":
        problems.append("a classifier failure on the newer comment fell back to the older clean review")
    if "classifier exited 7" not in stderr:
        problems.append("the classifier failure is not logged")
    return problems


def check_decision_log():
    """Each comment's decision reaches stderr with its reason (gha#1288)."""
    comments = [
        comment(review(), "NONE", created="2026-10-22T23:00:00Z"),
        comment(review(marker=False), created="2026-10-22T22:00:00Z"),
        comment(review(sha=OLD), created="2026-10-22T21:00:00Z"),
        comment(review()),
    ]
    _, stderr = run_finder_full(comments)
    wanted = [
        "author_association NONE is not",
        "has no agent marker",
        f"names {OLD}, not the head",
        "counts: a clean review of the head",
    ]
    return [f"decision log lacks {text!r}" for text in wanted if text not in stderr]


def main():
    failures = 0
    for name, comments, expected in CASES:
        found = run_finder(comments)["found"] == "true"
        status = "ok" if found == expected else "FAIL"
        if found != expected:
            failures += 1
        print(f"{status}: {name} (found={found}, expected={expected})")
    for problem in check_classifier_failure() + check_decision_log():
        failures += 1
        print(f"FAIL: {problem}")
    for problem in check_wiring():
        failures += 1
        print(f"FAIL: wiring: {problem}")
    print(f"{len(CASES)} finder cases, {failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
