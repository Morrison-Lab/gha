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
from typing import Callable, Tuple, Union


# A code fence: three or more backticks or tildes, then the info string's
# first word (the language) in group 2.
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)")

# A code span: a backtick run, its contents, and a closing run of exactly the
# same length, as CommonMark reads it.  The lookarounds stop a run from
# matching part of a longer one, so ``a``b`` is one span and `a``b` is one
# span, where the plain ``(`+).+?\1`` closed both early (gha#1856).
CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")

# The same span over a paragraph's text, where CommonMark lets a span run
# across a line break.  Use it only on text that is one paragraph or one
# body, never on a whole file.
PARAGRAPH_CODE_SPAN_RE = re.compile(CODE_SPAN_RE.pattern, re.S)


def mask_code_spans(line: str) -> str:
    """Blank every code span on one line, keeping the line's length."""
    return CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), line)


def replace_comments(
    text: str,
    repl: Union[str, Callable[[str], str]] = "",
    bang: bool = False,
) -> str:
    """Replace each closed ``<!-- ... -->`` in ``text`` with ``repl``.

    ``repl`` is a string, or a function given the comment's text that returns
    its replacement.  With ``bang``, ``--!>`` also closes a comment, as an HTML
    parser reads it.  An unclosed ``<!--`` and the text after it stay.

    A scan with ``find`` rather than a regex such as ``<!--.*?-->``, which
    CodeQL flags as bad HTML filtering; the scan closes each comment at the
    same place that regex does (gha#1856).
    """
    out = []
    pos = 0
    while True:
        start = text.find("<!--", pos)
        if start < 0:
            break
        end, width = text.find("-->", start + 4), 3
        if bang:
            alt = text.find("--!>", start + 4)
            if alt >= 0 and (end < 0 or alt < end):
                end, width = alt, 4
        if end < 0:
            break
        comment = text[start:end + width]
        out.append(text[pos:start])
        out.append(repl(comment) if callable(repl) else repl)
        pos = end + width
    out.append(text[pos:])
    return "".join(out)


def blank_closed_comments(line: str) -> str:
    """Blank each ``<!-- ... -->`` that opens and closes on this line.

    The comment-open state is carried across lines by the caller, so only
    comments closed on this line are blanked.
    """
    return replace_comments(line, lambda c: " " * len(c))


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
    return mask_code_spans(out), in_comment
