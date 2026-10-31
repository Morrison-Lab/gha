#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a page that a pull request adds to when the page has grown too long.

A long Quarto page is slow: MathJax typesets every formula in the browser, so
a page with a thousand formulas takes many seconds to finish rendering, and
a very tall page shrinks the scroll bar to its smallest length, which makes
the bar useless for finding a place (Ezra, 2026-10-31). The lab's rule is to
split such a page into several pages (psw ``chapters/teaching.qmd``, "Split a
page before it grows too long").

The goal is that a page loads and finishes rendering its math in under 5
seconds, and that its scroll bar is not at its smallest length. The check runs
without a browser, so it measures two proxies of the *expanded* page, which is
the page's own text with every ``{{< include >}}`` shortcode replaced by the
file it names:

- ``CPL_MAX_MATH`` (default 600): math expressions, display and inline. About
  8 ms each puts 600 expressions near the 5-second goal on a mid-range laptop.
- ``CPL_MAX_LINES`` (default 5000): source lines, a coarse proxy for rendered
  height. Semantic line breaks put one sentence on a line, so a line is
  roughly one rendered line to three.

Both are estimates to be tuned against measured render times; the decision and
its calibration are recorded in ``website/reference/check-page-length.qmd``.

What is flagged: a page (a ``.qmd`` file with a ``title:``) whose expanded text
passes either limit, when the diff adds a line to the page or to a file it
includes. The finding sits on the first added line.

What is not flagged: a page the diff did not touch, and a page carrying
``<!-- check-page-length: allow -->`` anywhere in its own file.

Design notes, in the model of ``check-heading-levels``:

- **Diff-scoped by default.** Existing long pages are not reflagged until an
  edit adds to them; nothing is swept.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``CPL_WHOLE_TREE=true`` scans
  every page, to measure a corpus.
- **Warn-only by default** (``CPL_FAIL`` defaults to false).

Configuration (environment variables, set by the composite action):
  CPL_BASE_REF      Git ref/SHA to diff against.
  CPL_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  CPL_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  CPL_FAIL          "true" => exit 1 on a finding; default "false".
  CPL_WHOLE_TREE    "true" => scan every tracked matching page in full.
  CPL_MAX_MATH      Math-expression limit (default 600).
  CPL_MAX_LINES     Source-line limit (default 5000).
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

DEFAULT_GLOBS = "*.qmd"
DEFAULT_MAX_MATH = 600
DEFAULT_MAX_LINES = 5000
ALLOW_MARKER = "check-page-length: allow"

INCLUDE_RE = re.compile(r"\{\{<\s*include\s+(\S+?)\s*>\}\}")
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
DISPLAY_RE = re.compile(r"\$\$.+?\$\$", re.DOTALL)
INLINE_RE = re.compile(r"(?<![\\$])\$(?!\$)[^$\n]+?(?<!\\)\$")
TITLE_RE = re.compile(r"^title:", re.MULTILINE)


class Finding(NamedTuple):
    line: int
    kind: str
    count: int
    limit: int
    math: int
    lines: int


def read_text(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def is_page(text: str) -> bool:
    """A page has a ``title:`` in its front matter; anything else is an include."""
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    return end > 0 and bool(TITLE_RE.search(text[:end]))


def resolve_include(target: str, current: str, root: str) -> Optional[str]:
    """An include's file: beside the includer, or at the root."""
    for base in (os.path.dirname(current), root):
        cand = os.path.normpath(os.path.join(base, target))
        if os.path.isfile(cand):
            return cand
    return None


def expand(path: str, root: str, seen: Tuple[str, ...] = ()) -> Tuple[str, Set[str]]:
    """The page's text with includes inlined, and every file it read."""
    real = os.path.realpath(path)
    files = {os.path.normpath(path)}
    text = read_text(path)
    if text is None or real in seen:
        return "", files
    out: List[str] = []
    pos = 0
    for m in INCLUDE_RE.finditer(text):
        out.append(text[pos:m.start()])
        target = resolve_include(m.group(1), path, root)
        if target:
            sub, sub_files = expand(target, root, seen + (real,))
            out.append(sub)
            files |= sub_files
        pos = m.end()
    out.append(text[pos:])
    return "".join(out), files


def strip_code(text: str) -> str:
    """Drop fenced code blocks and HTML comments, which hold no math."""
    kept: List[str] = []
    fence: Optional[Tuple[str, int]] = None
    for line in text.split("\n"):
        m = FENCE_RE.match(line)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        kept.append(line)
    return COMMENT_RE.sub("", "\n".join(kept))


def count_math(text: str) -> int:
    """Display and inline math expressions outside code and comments."""
    bare = strip_code(text)
    display = len(DISPLAY_RE.findall(bare))
    rest = DISPLAY_RE.sub("", bare)
    return display + len(INLINE_RE.findall(rest))


def measure(text: str) -> Tuple[int, int]:
    """(math expressions, source lines) of an expanded page."""
    return count_math(text), len(text.splitlines())


def over_limit(math: int, lines: int, max_math: int, max_lines: int
               ) -> Optional[Tuple[str, int, int]]:
    """The first limit passed, as (kind, count, limit), or None."""
    if math > max_math:
        return "math", math, max_math
    if lines > max_lines:
        return "lines", lines, max_lines
    return None


def format_message(f: Finding) -> str:
    what = ("math expressions" if f.kind == "math" else "source lines")
    return (f"This page now has {f.math} math expressions and {f.lines} "
            f"source lines once its includes are expanded, over the limit of "
            f"{f.limit} {what}, so it may take longer than 5 seconds to finish "
            f"rendering its math or shrink the scroll bar to its smallest "
            f"length. Fix: split the page into several pages, each a "
            f"coherent topic; keep the old section ids as stubs that link to "
            f"the new pages")


def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff: str) -> Dict[str, List[int]]:
    """``{path: [added line numbers]}`` of non-blank added lines."""
    added: Dict[str, List[int]] = {}
    path: Optional[str] = None
    old_left = new_left = new_line = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("+"):
                if path is not None and line[1:].strip():
                    added[path].append(new_line)
                new_line += 1
                new_left -= 1
            elif line.startswith("-"):
                old_left -= 1
            continue
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = (None if target == "/dev/null"
                    else target[2:] if target.startswith("b/") else target)
            if path is not None:
                added.setdefault(path, [])
            continue
        m = _HUNK_RE.match(line)
        if m:
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_line = int(m.group(2))
            new_left = int(m.group(3)) if m.group(3) is not None else 1
    return added


def _glob_to_regex(pat: str) -> "re.Pattern[str]":
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
    return default if not value else value in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    pages: int
    skipped: bool


def scan_page(path: str, root: str, touched: Optional[Dict[str, List[int]]],
              max_math: int, max_lines: int) -> Optional[Finding]:
    """A finding for ``path`` if it is over a limit and the diff touched it.

    ``touched`` maps a file to its added lines; None means scan regardless
    (whole-tree), reporting on line 1.
    """
    text, files = expand(path, root)
    if not text or ALLOW_MARKER in (read_text(path) or ""):
        return None
    math, lines = measure(text)
    hit = over_limit(math, lines, max_math, max_lines)
    if hit is None:
        return None
    line = 1
    if touched is not None:
        own = touched.get(os.path.normpath(path))
        if own:
            line = own[0]
        elif not any(touched.get(f) for f in files):
            return None
    return Finding(line, hit[0], hit[1], hit[2], math, lines)


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool, max_math: int, max_lines: int) -> Report:
    root = os.getcwd()
    touched: Optional[Dict[str, List[int]]] = None
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, True)
        candidates = [r for r in out.splitlines() if r]
    else:
        if not base_ref:
            return Report([], 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", "*.qmd"])
        if diff is None:
            return Report([], 0, True)
        touched = {os.path.normpath(k): v for k, v in parse_diff(diff).items()}
        listing = _run_git(["ls-files", "--", *globs])
        candidates = [r for r in (listing or "").splitlines() if r]
    findings: List[Tuple[str, Finding]] = []
    pages = 0
    for rel in sorted(candidates):
        if _ignored(rel, ignores):
            continue
        text = read_text(rel)
        if text is None or not is_page(text):
            continue
        pages += 1
        found = scan_page(rel, root, touched, max_math, max_lines)
        if found:
            findings.append((rel, found))
    return Report(findings, pages, False)


def main() -> int:
    base_ref = os.environ.get("CPL_BASE_REF", "").strip()
    globs = os.environ.get("CPL_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("CPL_PATHS_IGNORE", "")))
    fail = _env_flag("CPL_FAIL", False)
    whole_tree = _env_flag("CPL_WHOLE_TREE", False)
    max_math = _env_int("CPL_MAX_MATH", DEFAULT_MAX_MATH)
    max_lines = _env_int("CPL_MAX_LINES", DEFAULT_MAX_LINES)

    report = run_check(base_ref, globs, ignores, whole_tree, max_math, max_lines)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the page-length check for this run ({reason}; "
              f"not falling back to a whole-tree scan, which would reflag "
              f"every long page the corpus already carries).")
        return 0
    scope = "whole tree" if whole_tree else f"pages touched since {base_ref}"
    print(f"Measured {report.pages} page(s) (scope: {scope}; limits: "
          f"{max_math} math expressions, {max_lines} source lines).")
    severity = "error" if fail else "warning"
    for rel, f in report.findings:
        print(f"::{severity} file={rel},line={f.line}::{format_message(f)}")
    if not report.findings:
        print("No touched page is over the length limits.")
        return 0
    print(f"\n{len(report.findings)} page(s) are over the length limits.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
