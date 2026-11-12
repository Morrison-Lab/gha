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
- **Fails by default** (``CWI_FAIL`` defaults to true).
- **The search space is reported.** Every run prints how many files and lines
  it examined.

Configuration (environment variables, set by the composite action):
  CWI_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  CWI_GLOBS         Space-separated git pathspecs.
  CWI_PATHS_IGNORE  Comma/newline-separated glob patterns to skip (``*``,
                    ``?`` and recursive ``**``).
  CWI_FAIL          "true" => exit 1 on a finding; default "true" (set "false"
                    to warn only).
  CWI_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

DEFAULT_GLOBS = "*.qmd *.md"
_DEFAULT_FAIL = True

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


# The one `git diff` invocation every diff-scoped check uses. Fixed prefixes:
# diff.mnemonicPrefix would print `w/` and make every touched file read as
# missing (gha#1355, gha#1357).
GIT_DIFF_ARGS = ["diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv",
                 "--src-prefix=a/", "--dst-prefix=b/"]

# The checks that load this script as their engine, and its tests, read these
# names from it; the code is check-common's (gha#1856).
parse_diff = diffscope.parse_diff
compile_globs = diffscope.compile_ignores


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    skipped: bool


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
        # -z, so a name holding a quote, backslash or tab is read (gha#1923).
        paths = diffscope.git_paths(["ls-files", "--", *globs])
        if paths is None:
            return Report([], 0, 0, True)
        for rel in paths:
            if not diffscope.ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, True)
        diff = diffscope.run_git([*GIT_DIFF_ARGS, base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, True)
        added, deleted = parse_diff(diff)
        for rel, numbered in added.items():
            if diffscope.ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if not (text.strip() and text in deleted)}

    findings: List[Tuple[str, Finding]] = []
    files = lines = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
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
         format_finding=None, always_fail=frozenset(),
         default_fail=None, warn_only=frozenset()) -> int:
    """Run the check from the environment; the keyword arguments let a sibling
    check reuse the engine with its own scanner, env prefix and wording.
    A finding whose ``rule`` is in ``always_fail`` is an error and fails the
    run whatever the FAIL flag says.
    A finding whose ``rule`` is in ``warn_only`` is only a warning and never
    fails the run (a new rule's trial period); ``always_fail`` wins.
    ``default_fail`` is the FAIL default for a sibling check; None uses this
    check's own ``_DEFAULT_FAIL``."""
    base_ref = os.environ.get(prefix + "BASE_REF", "").strip()
    globs = os.environ.get(prefix + "GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(diffscope.split_list(os.environ.get(prefix + "PATHS_IGNORE", "")))
    fail = diffscope.env_flag(prefix + "FAIL",
                              _DEFAULT_FAIL if default_fail is None else default_fail)
    whole_tree = diffscope.env_flag(prefix + "WHOLE_TREE", False)
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

    blocking = False
    for rel, finding in report.findings:
        rule = getattr(finding, "rule", None)
        hard = rule in always_fail
        errors = hard or (fail and rule not in warn_only)
        blocking = blocking or errors
        severity = "error" if errors else "warning"
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{describe(finding)}")
    print(f"\n{len(report.findings)} line(s) {summary}")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
