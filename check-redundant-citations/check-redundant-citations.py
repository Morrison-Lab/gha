#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a source cited twice in one div or passage.

The lab's rule (Ezra, 2026-10-19; Morrison-Lab/psw#282): cite a source once
per div or passage, at the claim it supports. A second citation of the same
source, with the same locator, adds a number the reader must look up again and
tells them nothing new. Cite again only for a different part of the source,
and then give a locator.

What is flagged, in ``.qmd``/``.md`` files: within one block, a citation key
that occurs twice with the same locator (or with none). A block runs from one
``:::`` line (or ``{{< slidebreak >}}``) to the next, so a div and the prose
between divs are each a block.

What counts as a citation:

- every key in a bracketed citation, ``[@key]``, ``[@key, p. 5]`` or
  ``[@a; @b, p. 5]``, which may span lines;
- every ``@key`` on a line that starts with ``Source:``.

What is not flagged:

- an in-text citation (``@key [p. 5]`` or ``@key recommend ...``), because the
  author is the subject of the sentence, not a second pointer to the source;
- the same key with a different locator: that cites a different part;
- the same key in different list items: each item is its own claim, as in a
  list of video timestamps;
- cross-references (``@def-``, ``@eq-``, ``@fig-`` and the like), code fences,
  and chunk options (``#|`` lines).

Design notes, in the model of ``check-wikipedia-further-reading``:

- **Diff-scoped by default.** A repeat is reported only when one of its
  occurrences is on a line *added* since ``RC_BASE_REF``. The whole file is
  parsed, because the first citation can sit far above the added one. An
  added line whose exact text was also deleted in the same diff counts as
  moved, not new.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed (a shallow clone), the check skips with a warning.
  ``RC_WHOLE_TREE=true`` asks for the whole tree explicitly.
- **Warn-only by default** (``RC_FAIL`` defaults to false): the same key twice
  is sometimes right, for instance the same book with the same locator for two
  separate claims, so the first version annotates and does not block.
- **The search space is reported**: files, lines and blocks examined.

Configuration (environment variables, set by the composite action):
  RC_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                   skip the check.
  RC_GLOBS         Space-separated git pathspecs (default: '*.qmd *.md').
  RC_PATHS_IGNORE  Comma/newline-separated glob patterns (relative paths) to
                   skip. Supports ``*``, ``?`` and recursive ``**``.
  RC_FAIL          "true" => exit 1 on a finding; default "false" => warning
                   annotations only.
  RC_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import os
import re
import subprocess
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd *.md"
_DEFAULT_FAIL = False

# -- Rule tables -------------------------------------------------------------

# Cross-reference prefixes: ``@def-x`` points inside the document.
XREF_PREFIXES = (
    "def-", "thm-", "lem-", "prp-", "cor-", "exm-", "exr-", "rem-", "eq-",
    "fig-", "tbl-", "sec-", "sol-", "lst-", "nte-", "tip-", "wrn-", "imp-",
    "cau-",
)

ADVICE = (
    "cite a source once per div or passage, at the claim it supports; "
    "cite it again only for a different part, with a locator"
)

# -- Parsing -----------------------------------------------------------------

FENCE_RE = re.compile(r"^[ \t>]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^\s{0,3}:{3,}")
SLIDEBREAK_RE = re.compile(r"^\s*\{\{<\s*slidebreak")
ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])[ \t]+")
KEY_RE = re.compile(r"@([A-Za-z_][\w:.\-]*\w|[A-Za-z_])")
SOURCE_RE = re.compile(r"^\s*Source:")


class Finding(NamedTuple):
    line: int
    key: str
    locator: str
    first_line: int


def _bracket_groups(text: str) -> List[Tuple[int, str]]:
    """``(offset, inside)`` of each ``[...]`` group containing an ``@key``.

    Brackets are matched by depth, so a link such as ``[text](url)`` inside is
    never mistaken for the end of the group. Groups may span lines because
    ``text`` is a whole block joined with newlines.
    """
    groups = []
    stack: List[int] = []
    for i, ch in enumerate(text):
        if ch == "[":
            stack.append(i)
        elif ch == "]" and stack:
            start = stack.pop()
            inside = text[start + 1:i]
            if "@" in inside and not stack:
                groups.append((start + 1, inside))
    return groups


def _citations_in_group(inside: str) -> List[Tuple[str, str, int]]:
    """``(key, locator, offset)`` for each ``;``-separated citation."""
    out = []
    pos = 0
    for part in inside.split(";"):
        m = KEY_RE.search(part)
        if m and not m.group(1).startswith(XREF_PREFIXES):
            rest = part[m.end():]
            loc = " ".join(rest.split(",", 1)[1].split()) if "," in rest else ""
            out.append((m.group(1), loc, pos + m.start()))
        pos += len(part) + 1
    return out


def scan_block(block: List[Tuple[int, str, int]]) -> List[Finding]:
    """Repeated ``(key, locator)`` pairs in one block.

    ``block`` is ``[(line_number, text, item_id)]``. Returns one finding per
    repeat occurrence (every occurrence after the first), at its line.
    """
    # Offsets of each line's start in the joined text.
    starts, joined, pos = [], [], 0
    for _n, text, _item in block:
        starts.append(pos)
        joined.append(text)
        pos += len(text) + 1
    body = "\n".join(joined)

    def line_of(offset: int) -> int:
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo

    seen: Dict[Tuple[str, str, int], int] = {}
    found: List[Finding] = []

    def note(key: str, loc: str, idx: int) -> None:
        item = block[idx][2]
        ident = (key, loc, item)
        lineno = block[idx][0]
        if ident in seen:
            found.append(Finding(lineno, key, loc, seen[ident]))
        else:
            seen[ident] = lineno

    events = []  # (offset, key, locator)
    for off, inside in _bracket_groups(body):
        for key, loc, rel in _citations_in_group(inside):
            events.append((off + rel, key, loc))
    for idx, text in enumerate(joined):
        if SOURCE_RE.match(text):
            for m in KEY_RE.finditer(text):
                if not m.group(1).startswith(XREF_PREFIXES):
                    events.append((starts[idx] + m.start(), m.group(1), ""))
    for off, key, loc in sorted(events):
        note(key, loc, line_of(off))
    return found


def scan_file(lines: List[str]) -> Tuple[List[Finding], int]:
    """Findings in a file and the number of blocks examined."""
    fence: Optional[Tuple[str, int]] = None
    blocks: List[List[Tuple[int, str, int]]] = [[]]
    item = 0
    for idx, raw in enumerate(lines):
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m:
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if DIV_RE.match(raw) or SLIDEBREAK_RE.match(raw):
            blocks.append([])
            continue
        if raw.lstrip().startswith("#|"):
            continue
        if ITEM_RE.match(raw):
            item += 1
        blocks[-1].append((idx + 1, raw, item))
    findings: List[Finding] = []
    examined = 0
    for block in blocks:
        if any("@" in text for _n, text, _i in block):
            examined += 1
            findings.extend(scan_block(block))
    return findings, examined


# -- Messages ----------------------------------------------------------------

def format_message(f: Finding) -> str:
    where = f" {f.locator}" if f.locator else ""
    return (f"@{f.key}{where} is already cited at line {f.first_line} of this "
            f"div or passage. Fix: {ADVICE}")


# -- Git plumbing ------------------------------------------------------------

def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff: str) -> Tuple[Dict[str, Dict[int, str]], Set[str]]:
    """Added ``{path: {line_number: text}}`` and the set of deleted texts.

    Hunk header counts decide where a hunk ends, so an added line that begins
    with two plus signs is never mistaken for a ``+++`` file header.
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
            target = line[4:].rstrip("\t")
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


def _glob_to_regex(pat: str) -> "re.Pattern[str]":
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
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def _ignored(rel: str, ignores: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in ignores)


def _split_list(value: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,\n]", value) if p.strip()]


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    blocks: int
    skipped: bool


def _read_lines(path: str) -> Optional[List[str]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return None
    if lines and lines[-1] == "":
        lines.pop()  # the newline ending the file does not start a line
    return lines


def select_findings(findings: List[Finding],
                    keep: Optional[Set[int]]) -> List[Finding]:
    """Repeats where the repeat or its first citation is on a kept line.

    ``keep=None`` keeps every line (whole-tree mode).
    """
    if keep is None:
        return list(findings)
    return [f for f in findings if f.line in keep or f.first_line in keep]


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Scan the added lines since ``base_ref``, or every line when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, 0, True)
        for rel in out.splitlines():
            if rel and not _ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, 0, True)
        added, deleted = parse_diff(diff)
        for rel, numbered in added.items():
            if _ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if not (text.strip() and text in deleted)}

    findings: List[Tuple[str, Finding]] = []
    files = lines = blocks = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        found, examined = scan_file(content)
        blocks += examined
        for f in select_findings(found, keep):
            findings.append((rel, f))
    return Report(findings, files, lines, blocks, False)


def main() -> int:
    base_ref = os.environ.get("RC_BASE_REF", "").strip()
    globs = os.environ.get("RC_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("RC_PATHS_IGNORE", "")))
    fail = _env_flag("RC_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("RC_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(
            f"::warning::Skipping the redundant-citations check for this "
            f"run ({reason}; not falling back to a whole-tree scan, which "
            f"would reflag every repeat the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s), "
        f"{report.blocks} div(s) or passage(s) with a citation (scope: {scope})."
    )
    if not report.findings:
        print("No source is cited twice in one div or passage.")
        return 0

    severity = "error" if fail else "warning"
    for rel, f in report.findings:
        print(f"::{severity} file={rel},line={f.line}::{format_message(f)}")
    print(f"\n{len(report.findings)} repeated citation(s) in one div or passage.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
