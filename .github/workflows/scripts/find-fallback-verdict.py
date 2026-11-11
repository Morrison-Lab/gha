#!/usr/bin/env python3
"""Find a recorded fallback review verdict for a PR head (gha#1163).

Usage: find-fallback-verdict.py <comments.json> <head-sha> <classifier.sh>

<comments.json> is the JSON array the issue-comments API returns for a PR.
When the Claude review could not run (quota exhausted), the lab's fallback is
a separate-agent review posted as a PR comment. This script reports whether
such a comment exists for the CURRENT head and states a clean verdict.

A comment counts only when all of these hold:
  - its author_association is OWNER, MEMBER or COLLABORATOR, so it has the
    standing of someone who can already merge. The PR author's own comment
    counts: the lab's agent sessions post under the account holder's login,
    so excluding the author would reject the real fallback review;
  - it carries the agent-authorship marker, so a human note is not mistaken
    for a review;
  - the LAST "Reviewed-Commit:" (or "Reviewed commit:") line of its own
    prose names the full 40-character head sha, so a push retires it with no
    extra logic, and a comment listing several commits counts only for the
    one it ends on (gha#1229);
  - the marker and the sha line sit in the comment's own prose, not in a
    fenced code block, a blockquote or an indented code block, so quoting
    another review does not count as posting one;
  - the classifier reads its verdict as clean. A classifier that fails on
    one comment skips that comment rather than aborting the search
    (gha#1229).

Each comment's decision is logged to stderr, with the reason it did or did
not count, so a miss in CI can be read from the job log (gha#1288).

Prints found=true|false and url=<comment html_url> to stdout, and to
$GITHUB_OUTPUT when set. Exits 0 either way: the caller decides what a miss
means. Exits 2 on a usage or input error.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
MARKER = "not written by a human"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
QUOTE = re.compile(r"^ {0,3}>")


def own_prose(body):
    """Return the body without fenced, blockquoted or indented-code lines."""
    kept = []
    fence = None
    previous_blank = True
    indented_code = False
    for line in body.replace("\r", "").split("\n"):
        opener = FENCE.match(line)
        indented = line.startswith(("    ", "\t"))
        if indented_code and not (indented or not line.strip()):
            indented_code = False
        if indented_code:
            pass
        elif fence:
            closes = (
                opener
                and opener.group(1)[0] == fence[0]
                and len(opener.group(1)) >= len(fence)
                and not line.strip().strip(fence[0])
            )
            if closes:
                fence = None
        elif opener:
            fence = opener.group(1)
        elif indented and previous_blank:
            indented_code = True
        elif not QUOTE.match(line):
            kept.append(line)
        previous_blank = not line.strip()
    return "\n".join(kept)


def reviewed_commits(body):
    """Return the lower-cased shas named on Reviewed-Commit lines in the comment's own prose."""
    pattern = r"(?im)^ {0,3}Reviewed[- ]commit:\s*`?([0-9a-f]{7,40})`?\s*$"
    return [m.group(1).lower() for m in re.finditer(pattern, own_prose(body))]


def is_clean(body, head_sha, classifier):
    """Run the shared classifier on the comment text."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
        handle.write(body)
        path = handle.name
    try:
        result = subprocess.run(
            ["bash", classifier, path, "0", head_sha],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "GITHUB_OUTPUT": "/dev/null"},
        )
    finally:
        os.unlink(path)
    return "clean=true" in result.stdout.splitlines()


def find(comments, head_sha, classifier):
    """Return the html_url of the newest review of this head if it is clean, else "".

    The newest trusted, marked review that names the head decides, so a later
    not-clean review of the same head withdraws an earlier clean one.
    """
    for comment in sorted(comments, key=lambda c: c.get("created_at", ""), reverse=True):
        body = comment.get("body") or ""
        association = comment.get("author_association")
        if association not in TRUSTED_ASSOCIATIONS:
            log(comment, f"skipped: author_association {association} is not OWNER, MEMBER or COLLABORATOR")
            continue
        if MARKER not in own_prose(body).lower():
            log(comment, f"skipped: {association} comment has no agent marker in its own prose")
            continue
        commits = reviewed_commits(body)
        if not commits:
            log(comment, "skipped: no Reviewed-Commit line in its own prose")
            continue
        if commits[-1] != head_sha:
            log(comment, f"skipped: its last Reviewed-Commit line names {commits[-1]}, not the head")
            continue
        try:
            clean = is_clean(body, head_sha, classifier)
        except subprocess.CalledProcessError as error:
            log(comment, f"skipped: the classifier exited {error.returncode}")
            print(
                f"::warning::find-fallback-verdict: the classifier failed on {comment.get('html_url')}; skipping it.",
                file=sys.stderr,
            )
            continue
        if clean:
            log(comment, "counts: a clean review of the head")
            return comment.get("html_url") or "unknown"
        log(comment, "decides: a not-clean review of the head, which withdraws any older clean one")
        return ""
    print("find-fallback-verdict: no trusted, marked review of the head counts", file=sys.stderr)
    return ""


def log(comment, decision):
    """Write one comment's decision to stderr, for the job log (gha#1288)."""
    where = comment.get("html_url") or "a comment without a URL"
    print(f"find-fallback-verdict: {where}: {decision}", file=sys.stderr)


def main(argv):
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    comments_path, head_sha, classifier = argv[1], argv[2].lower(), argv[3]
    if not FULL_SHA.match(head_sha):
        print(f"::error::head sha {argv[2]!r} is not a full 40-character sha.", file=sys.stderr)
        return 2
    with open(comments_path, encoding="utf-8") as handle:
        comments = json.load(handle)
    if not isinstance(comments, list):
        print("::error::comments file is not a JSON array.", file=sys.stderr)
        return 2
    url = find(comments, head_sha, classifier)
    lines = [f"found={'true' if url else 'false'}", f"url={url}"]
    print("\n".join(lines))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
