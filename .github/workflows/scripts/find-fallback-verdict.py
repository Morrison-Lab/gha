#!/usr/bin/env python3
"""Find a recorded fallback review verdict for a PR head (gha#1163).

Usage: find-fallback-verdict.py <comments.json> <head-sha> <classifier.sh>

<comments.json> is the JSON array the issue-comments API returns for a PR.
When the Claude review could not run (quota exhausted), the lab's fallback is
a separate-agent review posted as a PR comment. This script reports whether
such a comment exists for the CURRENT head and states a clean verdict.

A comment counts only when all of these hold:
  - its author_association is OWNER, MEMBER or COLLABORATOR. That shows a
    tie to the repository, not write access: an org member or collaborator
    without push rights also qualifies, and the agent marker below is plain
    text anyone can type. The PR author's own comment
    counts: the lab's agent sessions post under the account holder's login,
    so excluding the author would reject the real fallback review;
  - it carries the agent-authorship marker, so a human note is not mistaken
    for a review;
  - its LAST "Reviewed-Commit:" (or "Reviewed commit:") line names the full
    40-character head sha, so a push retires it with no extra logic, and a
    comment listing several shas speaks for the last one only (gha#1229);
  - the marker and the sha line sit in the comment's own prose, not in a
    fenced code block, a blockquote or an indented code block, so quoting
    another review does not count as posting one;
  - the classifier reads its verdict as clean.

The newest qualifying comment decides. If the classifier fails on it, the
search stops with found=false and a warning, rather than aborting, or
falling back to an older review the newest one may have withdrawn (gha#1229).

The head sha is the commit the review run was for (the caller passes it),
not the live PR head, so re-running an older run cannot go green on a
fallback recorded for a newer head (gha#1229).

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
    """Run the shared classifier on the comment text; None when it fails."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
        handle.write(body)
        path = handle.name
    try:
        result = subprocess.run(
            ["bash", classifier, path, "0", head_sha],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "GITHUB_OUTPUT": "/dev/null"},
        )
    finally:
        os.unlink(path)
    if result.returncode != 0:
        return None
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
        if reviewed_commits(body)[-1:] != [head_sha]:
            continue
        url = comment.get("html_url") or "unknown"
        verdict = is_clean(body, head_sha, classifier)
        if verdict is None:
            print(f"::warning::The verdict classifier failed on {url}; no fallback review accepted.", file=sys.stderr)
        return url if verdict else ""
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
