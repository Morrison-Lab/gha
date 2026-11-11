#!/usr/bin/env python3
"""Find a newer clean Claude review of the same head (gha#1365).

Usage: find-newer-review-verdict.py <comments.json> <head-sha> <run-id> <classifier.sh>

When two review runs review the same head and the older one is not clean,
its `require-clean-verdict` check stays red after the newer run passes, and
re-running only its failed jobs replays the same stored verdict. This script
lets the older run's gate defer to the newer one.

<comments.json> is the JSON array the issue-comments API returns for a PR.
A comment is a review posted by claude-code-review.yml's post-review job when
all of these hold:
  - it was posted by github-actions[bot], the account the posting job uses;
  - its first line is the "**Claude finished review**" header, and that line
    links a workflow run, read as the review's run id;
  - its last non-empty line is "Reviewed commit: <sha>", stamped by the
    posting job, naming the full head sha. Only the last line counts, so a
    review that quotes such a line elsewhere does not change which commit it
    is about.

The review with the highest run id decides. When that run is not newer than
<run-id> (the run asking), nothing newer exists and the answer is no. When it
is newer, the answer is yes only if the classifier reads it as clean, so a
newer not-clean review keeps the gate red.

It loads find-fallback-verdict.py from its own directory for the classifier
call, so keep the two scripts side by side.

Each comment's decision is logged to stderr.
Prints found=true|false and url=<comment html_url> to stdout, and to
$GITHUB_OUTPUT when set. Exits 0 either way, and 2 on a usage or input error.
"""
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys

POSTER = "github-actions[bot]"
HEADER = re.compile(r"^\*\*Claude finished review\*\*.*actions/runs/(\d+)")
STAMP = re.compile(r"^Reviewed commit: ([0-9a-f]{40})$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

_spec = importlib.util.spec_from_file_location(
    "find_fallback_verdict", pathlib.Path(__file__).with_name("find-fallback-verdict.py")
)
_fallback = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fallback)
is_clean = _fallback.is_clean


def log(comment, decision):
    """Write one comment's decision to stderr, for the job log."""
    where = comment.get("html_url") or "a comment without a URL"
    print(f"find-newer-review-verdict: {where}: {decision}", file=sys.stderr)


def review_of(comment):
    """Return (run_id, reviewed_sha) for a posted Claude review, else None."""
    if (comment.get("user") or {}).get("login") != POSTER:
        return None
    lines = [line.strip() for line in (comment.get("body") or "").replace("\r", "").split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        return None
    header = HEADER.match(lines[0])
    stamp = STAMP.match(lines[-1])
    if not header or not stamp:
        return None
    return int(header.group(1)), stamp.group(1)


def find(comments, head_sha, run_id, classifier):
    """Return the html_url of a newer clean review of this head, else ""."""
    reviews = []
    for comment in comments:
        found = review_of(comment)
        if found is None:
            continue
        review_run, reviewed = found
        if reviewed != head_sha:
            log(comment, f"skipped: run {review_run} reviewed {reviewed}, not this head")
            continue
        reviews.append((review_run, comment))
    if not reviews:
        print("find-newer-review-verdict: no posted review of this head", file=sys.stderr)
        return ""
    review_run, comment = max(reviews, key=lambda item: item[0])
    if review_run <= run_id:
        log(comment, f"decides: run {review_run} is the newest review of this head, not newer than run {run_id}")
        return ""
    try:
        clean = is_clean(comment.get("body") or "", head_sha, classifier)
    except subprocess.CalledProcessError as error:
        log(comment, f"decides: the classifier exited {error.returncode} on the newest review, so it does not count")
        return ""
    if clean:
        log(comment, f"counts: run {review_run} is a newer clean review of this head")
        return comment.get("html_url") or "unknown"
    log(comment, f"decides: run {review_run} is the newest review of this head, and it is not clean")
    return ""


def main(argv):
    if len(argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2
    comments_path, head_sha, run_id, classifier = argv[1], argv[2].lower(), argv[3], argv[4]
    if not FULL_SHA.match(head_sha):
        print(f"::error::head sha {argv[2]!r} is not a full 40-character sha.", file=sys.stderr)
        return 2
    if not run_id.isdigit():
        print(f"::error::run id {run_id!r} is not a number.", file=sys.stderr)
        return 2
    with open(comments_path, encoding="utf-8") as handle:
        comments = json.load(handle)
    if not isinstance(comments, list):
        print("::error::comments file is not a JSON array.", file=sys.stderr)
        return 2
    url = find(comments, head_sha, int(run_id), classifier)
    lines = [f"found={'true' if url else 'false'}", f"url={url}"]
    print("\n".join(lines))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
