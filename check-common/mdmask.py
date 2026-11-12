# check-one-function-per-file: allow-multiple
"""Shared Markdown masking for the diff-scoped checks (gha#1856).

A check that scans prose must skip code and comments, or it reports a phrase
that sits inside a code span, a fenced block or an HTML comment.  Several
checks carried the same copy of that masking, so a fix to one copy stayed out
of the others.  This module is the one copy, beside ``diffscope.py``: a check
puts this directory on ``sys.path`` and imports it.

``mask_markdown_line`` blanks code spans and HTML comments on one line and
carries an open comment across lines.  Fence state stays with the caller,
because the checks differ on which fences they read: ``check-local-macros``
reads ``tex`` fences that the others skip.  Each check matches ``FENCE_RE``
and keeps its own fence state.

Masked text keeps the line's length, so a column found in it is a column in
the source line.  Stdlib only.
"""

import re
from typing import Tuple


# A code fence: three or more backticks or tildes, then the info string's
# first word (the language) in group 2.
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)")

# A code span: a backtick run, its contents, and a closing run of the same
# length.
CODE_SPAN_RE = re.compile(r"(`+).+?\1")


def blank_closed_comments(line: str) -> str:
    """Blank each ``<!-- ... -->`` that opens and closes on this line.

    A scan with ``find`` rather than a regex: the comment-open state is
    carried across lines by the caller, so a one-line pattern is the wrong
    tool for an HTML comment, and CodeQL flags it as such.
    """
    out = line
    pos = 0
    while True:
        start = out.find("<!--", pos)
        if start < 0:
            return out
        end = out.find("-->", start + 4)
        if end < 0:
            return out
        out = out[:start] + " " * (end + 3 - start) + out[end + 3:]
        pos = end + 3


def mask_markdown_line(line: str, in_comment: bool) -> Tuple[str, bool]:
    """Blank code spans and HTML comments; track a comment open across lines.

    Returns the masked line and whether an HTML comment is still open at its
    end.  A line inside a comment that does not close returns ``""``.
    """
    out = line
    if in_comment:
        end = out.find("-->")
        if end < 0:
            return "", True
        out, in_comment = " " * (end + 3) + out[end + 3:], False
    out = blank_closed_comments(out)
    start = out.find("<!--")
    if start >= 0:
        out, in_comment = out[:start], True
    out = CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), out)
    return out, in_comment
