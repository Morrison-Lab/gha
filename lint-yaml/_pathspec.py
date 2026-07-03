"""
Shared glob-based path-ignore matching for lint-yaml's checks.

Kept local to this composite (not imported across composite directories) so
each capability in this repo stays independently taggable and self-contained;
the matching rules mirror check-phi's PHI_PATHS_IGNORE handling for
consistency, since both give callers the same GitHub-native paths-ignore
semantics.
"""

import re
import subprocess
from typing import List


def tracked_files(patterns: List[str], ignores: List["re.Pattern[str]"]) -> List[str]:
    """Git-tracked files matching any of ``patterns`` (git pathspecs, matched
    at any depth), filtered against ``ignores``."""
    out = subprocess.run(
        ["git", "ls-files", "--", *patterns],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [f for f in out if not is_ignored(f, ignores)]


def split_list(raw: str) -> List[str]:
    """Split a comma/newline-separated env-var value into stripped patterns."""
    parts = re.split(r"[,\n]", raw)
    return [p.strip() for p in parts if p.strip()]


def glob_to_regex(pat: str) -> "re.Pattern[str]":
    """Translate a path glob to an anchored regex. Supports ``**`` (any number
    of path segments), ``*`` (within a single segment), and ``?``. ``fnmatch``
    is not used because it treats ``**`` as two literal ``*`` (non-recursive)."""
    i, n, out = 0, len(pat), []
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i:i + 2] == "**":
                i += 2
                if pat[i:i + 1] == "/":
                    out.append("(?:.*/)?")  # **/  => zero or more leading dirs
                    i += 1
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")  # * stays within one path segment
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def compile_ignores(patterns: List[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(glob_to_regex(pat))
        # A bare directory name also gets an "everything beneath" expansion,
        # so "docs" skips "docs/x/y.yml" the way GitHub's native
        # paths-ignore does. Patterns that already use wildcards keep literal
        # single-segment semantics.
        if "*" not in pat and "?" not in pat:
            compiled.append(glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def is_ignored(path: str, ignores: List["re.Pattern[str]"]) -> bool:
    return any(pat.match(path) for pat in ignores)
