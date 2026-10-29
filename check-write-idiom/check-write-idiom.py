#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a line that opens with ``Write the``, ``Write a`` or ``Write an``.

The lab's rule (Morrison-Lab/gha#1121, from psw#297): in an exercise,
"Write ..." is ambiguous. It means derive, express, state or give, and the
instruction should name the action literally ("Derive an expression for",
"Express", "State", "Give").

What is flagged: in ``.qmd`` and ``.md`` files, a line that begins, after
optional whitespace, an optional list marker (``-``, ``*``, ``1.``, ``1)``)
and an optional label such as ``(a)`` or ``a)``, with ``Write the ``,
``Write a `` or ``Write an `` (case-sensitive ``Write``).

What is not flagged:

- ``Write $...$ for ...``, which is notation;
- ``Write down``;
- ``Write`` anywhere but at the start of the line;
- code fences and code spans, HTML comments, and YAML front matter;
- a line carrying, or following, ``<!-- check-write-idiom: allow -->``.

Design notes, in the model of ``check-fform-paren``, whose diff model and
Markdown masking are copied here rather than imported:

- **Diff-scoped by default.** Only lines *added* since ``CWI_BASE_REF`` are
  reported. An added line whose exact text was also deleted in the same diff
  is treated as moved. ``CWI_WHOLE_TREE=true`` scans everything.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning instead of scanning the whole tree.
- **Warn-only by default** (``CWI_FAIL`` defaults to false).
- **The search space is reported.** Every run prints how many files and lines
  it examined.

Configuration (environment variables, set by the composite action):
  CWI_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  CWI_GLOBS         Space-separated git pathspecs.
  CWI_PATHS_IGNORE  Comma/newline-separated glob patterns to skip (``*``,
                    ``?`` and recursive ``**``).
  CWI_FAIL          "true" => exit 1 on a finding.
  CWI_WHOLE_TREE    "true" => scan every tracked matching file in full.
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

# Optional whitespace, an optional list marker, an optional label, then the
# idiom. "Write" is case-sensitive; the trailing space keeps `Write $x$` and
# `Write down` out.
WRITE_RE = re.compile(
    r"^\s*(?:(?:[-*]|\d+[.)])\s+)?(?:\(?[A-Za-z0-9]{1,4}\)\s*)?"
    r"(Write (?:the|a|an)) "
)
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)")
ALLOW_RE = re.compile(r"<!--\s*check-write-idiom:\s*allow\s*-->")
CODE_SPAN_RE = re.compile(r"(`+).+?\1")

MESSAGE = (
    '"Write ..." means derive, express, state or give here; name the action '
    'literally ("Derive an expression for", "Express", "State", "Give") '
    "(psw#297)."
)


class Finding(NamedTuple):
    line: int
    phrase: str


def _blank_closed_comments(line: str) -> str:
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


def _mask_markdown_line(line: str, in_comment: bool) -> Tuple[str, bool]:
    """Blank code spans and HTML comments; track a comment open across lines."""
    out = line
    if in_comment:
        end = out.find("-->")
        if end < 0:
            return "", True
        out, in_comment = " " * (end + 3) + out[end + 3:], False
    out = _blank_closed_comments(out)
    start = out.find("<!--")
    if start >= 0:
        out, in_comment = out[:start], True
    out = CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), out)
    return out, in_comment


def scan_markdown(lines: List[str], check, allow_re) -> Tuple[List[Tuple[int, object]], int]:
    """``([(line number, payload), ...], lines examined)`` for a Markdown file.

    Skips YAML front matter, code fences, code spans, HTML comments, and a line
    carrying, or following, a comment that ``allow_re`` matches. ``check`` maps
    a masked line to the payloads it finds; a sibling check reuses this with
    its own ``check`` and ``allow_re``.
    """
    found: List[Tuple[int, object]] = []
    examined = 0
    fence: Optional[Tuple[str, int]] = None  # (marker, length)
    in_comment = False
    in_front = bool(lines) and lines[0].strip() == "---"
    for number, raw in enumerate(lines, 1):
        examined += 1
        if in_front:
            if number > 1 and raw.strip() in ("---", "..."):
                in_front = False
            continue
        m = FENCE_RE.match(raw)
        if fence is None and m and not in_comment:
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                    and not m.group(2):
                fence = None
            continue
        masked, in_comment = _mask_markdown_line(raw, in_comment)
        allowed = allow_re.search(raw) or (
            number > 1 and allow_re.search(lines[number - 2]))
        if allowed:
            continue
        for payload in check(masked):
            found.append((number, payload))
    return found, examined


def _write_phrases(masked: str) -> List[str]:
    hit = WRITE_RE.match(masked)
    return [hit.group(1)] if hit else []


def scan_file(lines: List[str]) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)`` for a Markdown-family file."""
    hits, examined = scan_markdown(lines, _write_phrases, ALLOW_RE)
    return [Finding(number, phrase) for number, phrase in hits], examined


def format_message(finding: Finding) -> str:
    return MESSAGE


def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


# The one `git diff` invocation every diff-scoped check uses. Fixed prefixes:
# diff.mnemonicPrefix would print `w/` and make every touched file read as
# missing (gha#1355, gha#1357).
GIT_DIFF_ARGS = ["diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv",
                 "--src-prefix=a/", "--dst-prefix=b/"]


_C_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13,
              '"': 34, "\\": 92}


def _unquote_git_path(target: str) -> str:
    """Undo git's C-style quoting of a path that holds ``"``, a backslash or a
    control character (``"b/ch/q\\"u.qmd"``); any other target is returned as is.
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
            digits = body[i + 1:i + 4]
            octal = ""
            for d in digits:
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
            target = _unquote_git_path(line[4:].rstrip("\t"))
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


def compile_globs(patterns: List[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def _matches(rel: str, globs: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in globs)


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
    skipped: bool


def _read_lines(path: str) -> Optional[List[str]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return None
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool, scan=None) -> Report:
    """Scan the added lines since ``base_ref``, or every line when whole-tree.

    ``scan`` is the per-file scanner (default ``scan_file``), so a sibling check
    such as ``check-avoided-words`` can reuse the diff model. A scanner with a
    true ``wants_scope`` attribute is called as ``scan(content, keep)``, with
    ``keep`` the set of added line numbers (``None`` for a whole-tree scan),
    and its findings are reported as returned, not filtered to ``keep``.
    """
    scan = scan or scan_file
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, True)
        for rel in out.splitlines():
            if rel and not _matches(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, True)
        diff = _run_git([*GIT_DIFF_ARGS, base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, True)
        added, deleted = parse_diff(diff)
        for rel, numbered in added.items():
            if _matches(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if not (text.strip() and text in deleted)}

    findings: List[Tuple[str, Finding]] = []
    files = lines = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        if getattr(scan, "wants_scope", False):
            # The scanner reads the added-line set itself (a file-level rule
            # fires when the file is touched at all) and returns what to report.
            findings.extend((rel, f) for f in scan(content, keep)[0])
            continue
        for finding in scan(content)[0]:
            if keep is None or finding.line in keep:
                findings.append((rel, finding))
    return Report(findings, files, lines, False)


def main(scan=None, prefix: str = "CWI_", name: str = "write-idiom",
         clean: str = 'No line opens with "Write the", "Write a" or "Write an".',
         summary: str = 'open with a vague "Write ...".',
         format_finding=None) -> int:
    """Run the check from the environment; the keyword arguments let a sibling
    check reuse the engine with its own scanner, env prefix and wording."""
    base_ref = os.environ.get(prefix + "BASE_REF", "").strip()
    globs = os.environ.get(prefix + "GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_globs(_split_list(os.environ.get(prefix + "PATHS_IGNORE", "")))
    fail = _env_flag(prefix + "FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag(prefix + "WHOLE_TREE", False)
    describe = format_finding or format_message

    report = run_check(base_ref, globs, ignores, whole_tree, scan)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        # With no base-ref (a push run) the skip is expected, so it is not an annotation.
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the {name} check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every use the repository already has)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.lines} line(s) across {report.files} file(s) "
          f"(scope: {scope}).")
    if not report.findings:
        print(clean)
        return 0

    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{describe(finding)}")
    print(f"\n{len(report.findings)} line(s) {summary}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
