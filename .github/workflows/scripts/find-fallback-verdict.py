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
  - it names the full 40-character head sha in a "Reviewed-Commit:" (or
    "Reviewed commit:") line, so a push retires it with no extra logic;
  - the marker and the sha line sit in the comment's own prose, not in a
    fenced code block, a blockquote or an indented code block, so quoting
    another review does not count as posting one;
  - the classifier reads its verdict as clean.

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
    for line in body.replace("\r", "").split("\n"):
        opener = FENCE.match(line)
        if fence:
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
        elif line.startswith(("    ", "\t")) and previous_blank:
            pass
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
        if comment.get("author_association") not in TRUSTED_ASSOCIATIONS:
            continue
        if MARKER not in own_prose(body).lower():
            continue
        if head_sha not in reviewed_commits(body):
            continue
        if is_clean(body, head_sha, classifier):
            return comment.get("html_url") or "unknown"
        return ""
    return ""


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
