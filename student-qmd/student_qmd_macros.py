# check-one-function-per-file: allow-multiple
"""Find LaTeX macro definitions, and drop the ones a document never uses.

A course's shared macro file can define thousands of macros, and a student
file that includes it opens with thousands of lines of `\\def` before the
first question. With `prune-macros` on, make_student_qmd.py keeps only the
definitions the document uses, directly or through another macro.

check_student_qmd.py uses `macro_groups` too, to take definitions out of the
comparison on both sides; it does not share the pruning itself. Pandoc
expands the macros it knows inside math, so a definition the student file
needed and lost changes the student file's math, and the comparison fails.

Ported from Morrison-Lab/epi204's scripts/generate-assign-qmd.R
(`macro_def_name`, `group_macro_defs`, `find_macro_refs`,
`filter_unused_macros`), gha#927.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# \def\name or \let\name, with a letter-only name.
DEF_LETTERS = re.compile(r"^\\(?:def|let)\\([A-Za-z]+)")
# \def\X, with a single character that is not a letter, digit or space.
DEF_SYMBOL = re.compile(r"^\\def\\([^A-Za-z0-9\s])")
# \newcommand{\name}, \renewcommand{\name}, \providecommand{\name}, with or
# without a star.
COMMAND = re.compile(r"^\\(?:provide|renew|new)command\*?\s*\{\\([A-Za-z0-9]+)\}")
ESCAPED_BRACE = re.compile(r"\\[{}]")


@dataclass(frozen=True)
class MacroDef:
    name: str
    start: int  # index of the definition's first line
    end: int  # index one past its last line


def macro_def_name(line: str) -> str | None:
    """The name a line starts defining, or None if it defines nothing."""
    for pattern in (DEF_LETTERS, DEF_SYMBOL, COMMAND):
        if m := pattern.match(line):
            return m.group(1)
    return None


def macro_groups(lines: list[str], skip: list[bool] | None = None) -> list[MacroDef]:
    """The macro definitions in `lines`, each possibly spanning lines.

    A definition runs until its unescaped braces balance. Lines marked in
    `skip`, such as code, never start one. Once a definition's braces fail
    to balance, no later line starts one either.
    """
    groups = []
    start: int | None = None
    name = ""
    depth = 0
    for i, line in enumerate(lines):
        if start is None:
            if skip is not None and skip[i]:
                continue
            found = macro_def_name(line)
            if found is None:
                continue
            start, name, depth = i, found, 0
        bare = ESCAPED_BRACE.sub("", line)
        depth += bare.count("{") - bare.count("}")
        if depth <= 0:
            groups.append(MacroDef(name, start, i + 1))
            start = None
    # A definition whose braces never balance is not taken for one, so
    # pruning cannot drop the rest of the document with it.
    return groups


def references(text: str, names: set[str]) -> set[str]:
    """The names in `names` that `text` uses as a command."""
    found = set()
    for name in names:
        if name.isascii() and name.isalpha():
            pattern = rf"\\{name}(?![A-Za-z])"
        else:
            pattern = r"\\" + re.escape(name)
        if re.search(pattern, text):
            found.add(name)
    return found


def prune_macros(lines: list[str], skip: list[bool] | None = None) -> list[str]:
    """`lines` without the macro definitions nothing uses.

    Every definition of a used name is kept, not only the first as epi204's
    script does: a later `\\def` of the same name replaces the earlier one in
    LaTeX and in Pandoc, so keeping only the first changes what the macro
    means, and the check fails on it.
    """
    groups = macro_groups(lines, skip)
    if not groups:
        return lines
    in_def = [False] * len(lines)
    for g in groups:
        for i in range(g.start, g.end):
            in_def[i] = True
    names = {g.name for g in groups}
    content = "\n".join(line for line, d in zip(lines, in_def) if not d)
    used = references(content, names)
    pending = set(used)
    while pending:
        body = "\n".join(
            "\n".join(lines[g.start : g.end]) for g in groups if g.name in pending
        )
        pending = references(body, names) - used
        used |= pending
    drop = [False] * len(lines)
    for g in groups:
        if g.name not in used:
            for i in range(g.start, g.end):
                drop[i] = True
    return [line for line, d in zip(lines, drop) if not d]
