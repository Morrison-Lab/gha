# check-one-function-per-file: allow-multiple
"""Shared diff scoping for the diff-scoped checks (gha#1856).

Most checks here report only lines a pull request adds, exempt a line that was
only moved, and skip when no base resolves.  Each one used to carry its own copy
of that machinery, so a fix to one copy stayed out of the others.  This module
is the one copy: a check puts this directory on ``sys.path`` and imports it.

A composite action runs from a checkout of this whole repository at the pinned
ref, so ``<action_path>/../check-common`` is always present beside the check.
Checks already rely on that when they load a sibling's script by relative path.

Stdlib only, like the checks that import it.
"""

import os
import re
import subprocess
from typing import Dict, List, Optional, Set, Tuple


# Settings a caller's git config could hold that change what ``parse_diff``
# reads: ``diff.mnemonicPrefix`` prints ``w/`` for ``b/``, so every touched file
# reads as missing (gha#1355), and ``diff.noprefix`` drops the prefix, so a top
# directory named ``b`` would be stripped.  Pinned here, they hold for every
# ``git diff`` a check runs through ``run_git``.
_GIT_CONFIG = ["-c", "core.quotepath=false",
               "-c", "diff.mnemonicPrefix=false",
               "-c", "diff.noprefix=false"]


def run_git(args: List[str]) -> Optional[str]:
    """The stdout of ``git args``, or None when git exits non-zero."""
    res = subprocess.run(
        ["git", *_GIT_CONFIG, *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

_C_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13,
              '"': 34, "\\": 92}


def unquote_git_path(target: str) -> str:
    """Undo git's C-style quoting of a path holding ``"``, a backslash or a
    control character (``"b/ch/q\\"u.qmd"``); any other target is returned as is.

    ``core.quotepath=false`` stops git quoting non-ASCII bytes, not these.
    """
    if len(target) < 2 or not (target.startswith('"') and target.endswith('"')):
        return target
    body = target[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        char = body[i]
        if char != "\\" or i + 1 >= len(body):
            out += char.encode("utf-8")
            i += 1
            continue
        nxt = body[i + 1]
        if nxt in _C_ESCAPES:
            out.append(_C_ESCAPES[nxt])
            i += 2
        elif nxt in "01234567":
            octal = ""
            for d in body[i + 1:i + 4]:
                if d not in "01234567":
                    break
                octal += d
            out.append(int(octal, 8) & 0xFF)
            i += 1 + len(octal)
        else:
            out += body[i:i + 2].encode("utf-8")
            i += 2
    return out.decode("utf-8", errors="replace")


def parse_diff(diff: str) -> Tuple[Dict[str, Dict[int, str]], Set[str]]:
    """Added ``{path: {line_number: text}}`` and the set of deleted texts.

    Hunk header counts decide where a hunk ends, so an added line that begins
    with two plus signs is never mistaken for a ``+++`` file header.
    Take the diff with ``-U0``: a context line advances no line counter.
    """
    added: Dict[str, Dict[int, str]] = {}
    deleted: Set[str] = set()
    path: Optional[str] = None
    old_left = new_left = new_line = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("+"):
                if path is not None:
                    added[path][new_line] = line[1:]
                new_line += 1
                new_left -= 1
            elif line.startswith("-"):
                deleted.add(line[1:])
                old_left -= 1
            continue
        if line.startswith("+++ "):
            target = unquote_git_path(line[4:].rstrip("\t"))
            path = None if target == "/dev/null" else target[2:] if target.startswith("b/") else target
            if path is not None:
                added.setdefault(path, {})
            continue
        m = _HUNK_RE.match(line)
        if m:
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_line = int(m.group(2))
            new_left = int(m.group(3)) if m.group(3) is not None else 1
    return added, deleted


def parse_renames(status: str) -> List[Tuple[str, str]]:
    """``(old, new)`` pairs from ``git diff --name-status -M`` output."""
    pairs: List[Tuple[str, str]] = []
    for line in status.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            pairs.append((parts[1], parts[2]))
    return pairs


_INCLUDE_RE = re.compile(r"\{\{<\s*include\s+(\S+?)\s*>\}\}")


def _names(path: str, target: str) -> bool:
    """Whether an include ``target`` can name the repository file ``path``."""
    target = target.removeprefix("./")
    return path == target or path.endswith("/" + target)


def is_repointed_include(text: str, deleted: Set[str],
                         renames: List[Tuple[str, str]]) -> bool:
    """An added include line that only follows a renamed file is moved.

    It counts when a deleted line reads the same with the old target, and the
    diff renames a file the old target names to one the new target names.
    """
    m = _INCLUDE_RE.search(text)
    if not m:
        return False
    new_target = m.group(1)
    for old, new in renames:
        if not _names(new, new_target):
            continue
        for line in deleted:
            o = _INCLUDE_RE.search(line)
            if (o and _names(old, o.group(1))
                    and line[:o.start(1)] + new_target + line[o.end(1):] == text):
                return True
    return False


def glob_to_regex(pat: str) -> "re.Pattern[str]":
    """Translate a path glob to an anchored regex; supports ``**``, ``*``, ``?``."""
    i, n, out = 0, len(pat), []
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i:i + 2] == "**":
                i += 2
                if pat[i:i + 1] == "/":
                    out.append("(?:.*/)?")
                    i += 1
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def compile_ignores(patterns: List[str]) -> List["re.Pattern[str]"]:
    """Regexes for ``paths-ignore``; a bare directory also ignores its contents."""
    compiled = []
    for pat in patterns:
        compiled.append(glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def ignored(rel: str, ignores: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in ignores)


def split_list(value: str) -> List[str]:
    """Items of a comma- or newline-separated input, trimmed, blanks dropped."""
    return [p.strip() for p in re.split(r"[,\n]", value) if p.strip()]


def env_flag(name: str, default: bool) -> bool:
    """A boolean environment input; empty means ``default``."""
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def read_lines(path: str) -> Optional[List[str]]:
    """A file's lines without their newlines, or None when it cannot be read."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return None
    if lines and lines[-1] == "":
        lines.pop()  # the newline ending the file does not start a line
    return lines
