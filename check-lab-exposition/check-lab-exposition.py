#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag expository content, such as a definition or a theoretical result, in a lab page.

The lab's rule (Ezra, 2026-11-19, psw "Keep expository content out of labs"):
a lab applies what the exposition pages teach, and introduces no new
expository content.
Every definition, theorem, lemma, proposition, corollary, conjecture and
remark lives on an exposition page, and the lab links to it.

A lab page is a tracked file matched by ``CLE_PAGES`` (default
``*-lab.qmd``).
Its content is the page plus every file it pulls in through
``{{< include >}}``, followed transitively.
An include target resolves against the top-level page's directory, as Quarto
resolves nested includes, and then against the including file's directory.
An escaped include (``{{</* include ... */>}}``) is not followed, because
Quarto does not expand it.

What is flagged, within a lab page's content:

- an opening fence of a div whose id has one of the ``CLE_PREFIXES``
  (default ``def thm lem prp cor cnj rem``), as in ``::: {#def-foo}``;
- an include line whose target, followed transitively, holds such a div.

A div or include is exempt when its opening line, or one of the three lines
after it, holds ``<!-- lab-exposition-ok: reason -->`` with a non-empty reason.
The search stops at the next div opener or include line, so one comment
exempts only the item it follows.

A path matched by ``CLE_PATHS_IGNORE`` is skipped as a lab page and as an
included file: its divs are not reported, an include of it is not flagged,
and includes are not followed through it.

No check can tell an explanation from an instruction, so prose exposition
outside a div is left to the writer and the reviewer; the psw rule says so.

Design notes, in the model of ``check-exm-figures``:

- **Diff-scoped by default.** A finding is reported only when its line is a
  line the diff adds, so the labs that already break the rule are not
  reflagged on every PR. An added line whose exact text was also deleted in
  the same diff is moved, not new.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``CLE_WHOLE_TREE=true`` scans
  every lab page in full, which lists the labs that break the rule.
- **Blocking by default** (``CLE_FAIL`` defaults to true).
- **The search space is reported**: lab pages, files reached and divs seen.

Configuration (environment variables, set by the composite action):
  CLE_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  CLE_PAGES         Space-separated git pathspecs of lab pages
                    (default: '*-lab.qmd').
  CLE_PREFIXES      Space-separated div-id prefixes that count as exposition
                    (default: 'def thm lem prp cor cnj rem').
  CLE_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  CLE_FAIL          "false" => warn only; default "true".
  CLE_WHOLE_TREE    "true" => scan every lab page in full.
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

DEFAULT_PAGES = "*-lab.qmd"
DEFAULT_PREFIXES = "def thm lem prp cor cnj rem"
_DEFAULT_FAIL = True

INCLUDE_RE = re.compile(r"\{\{<\s*include\s+(\S+?)\s*>\}\}")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
EXEMPT_RE = re.compile(r"<!--\s*lab-exposition-ok:\s*(?!-->)\S")
EXEMPT_REACH = 3
OPENER_RE = re.compile(r"^\s*:{3,}\s*\{")


def div_re(prefixes: List[str]) -> "re.Pattern[str]":
    alt = "|".join(re.escape(p) for p in prefixes)
    return re.compile(r"^\s*:{3,}\s*\{[^}]*#((?:" + alt + r")-[\w.:-]+)")


class FileScan(NamedTuple):
    divs: List[Tuple[int, str]]      # (line, id) of each exposition div opener
    includes: List[Tuple[int, str]]  # (line, raw target) of each include


def scan_lines(lines: List[str], pattern: "re.Pattern[str]") -> FileScan:
    """The exposition divs and the includes of one file, outside code fences."""
    divs: List[Tuple[int, str]] = []
    includes: List[Tuple[int, str]] = []
    fence: Optional[str] = None
    for n, line in enumerate(lines, 1):
        m = FENCE_RE.match(line)
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not line.strip()[len(m.group(1)):].strip():
                fence = None
            continue
        if m:
            fence = m.group(1)
            continue
        d = pattern.match(line)
        if d:
            divs.append((n, d.group(1)))
        for inc in INCLUDE_RE.finditer(line):
            includes.append((n, inc.group(1)))
    return FileScan(divs, includes)


def exempt(lines: List[str], line: int) -> bool:
    """Whether the opening line or one of the next few lines exempts it.

    The search stops at the next div opener or include line, so a comment
    that belongs to a later item does not exempt this one.
    """
    for k, text in enumerate(lines[line - 1: line + EXEMPT_REACH]):
        if k and (OPENER_RE.match(text) or INCLUDE_RE.search(text)):
            return False
        if EXEMPT_RE.search(text):
            return True
    return False


def resolve(target: str, page: str, including: str) -> Optional[str]:
    """The repository path an include target names, or None."""
    for base in (os.path.dirname(page), os.path.dirname(including)):
        cand = os.path.normpath(os.path.join(base, target))
        if os.path.isfile(cand):
            return cand
    return None


class Finding(NamedTuple):
    path: str
    line: int
    page: str
    what: str  # the div id, or the include target


class Report(NamedTuple):
    findings: List[Finding]
    pages: int
    files: int
    divs: int
    skipped: bool


class Corpus:
    """Reads, scans and caches each file once, and follows includes."""

    def __init__(self, pattern: "re.Pattern[str]", ignores: Optional[list] = None):
        self.pattern = pattern
        self.ignores = ignores or []
        self.lines: Dict[str, List[str]] = {}
        self.scans: Dict[str, FileScan] = {}

    def scan(self, path: str) -> Optional[FileScan]:
        if path not in self.scans:
            content = diffscope.read_lines(path)
            if content is None:
                return None
            self.lines[path] = content
            self.scans[path] = scan_lines(content, self.pattern)
        return self.scans[path]

    def reach(self, page: str) -> Dict[str, List[Tuple[int, str, Optional[str]]]]:
        """Every file the page renders, with its includes resolved."""
        out: Dict[str, List[Tuple[int, str, Optional[str]]]] = {}
        stack = [page]
        while stack:
            path = stack.pop()
            if path in out or diffscope.ignored(path, self.ignores):
                continue
            scan = self.scan(path)
            if scan is None:
                continue
            resolved = []
            for line, target in scan.includes:
                child = resolve(target, page, path)
                resolved.append((line, target, child))
                if child is not None:
                    stack.append(child)
            out[path] = resolved
        return out

    def holds_exposition(self, path: str, page: str, seen: Set[str]) -> bool:
        """Whether the file, or anything it includes, holds an unexempt exposition div."""
        if path in seen or diffscope.ignored(path, self.ignores):
            return False
        seen.add(path)
        scan = self.scan(path)
        if scan is None:
            return False
        lines = self.lines[path]
        if any(not exempt(lines, n) for n, _ in scan.divs):
            return True
        for n, target in scan.includes:
            if exempt(lines, n):
                continue
            child = resolve(target, page, path)
            if child is not None and self.holds_exposition(child, page, seen):
                return True
        return False


def run_check(base_ref: str, pages_globs: List[str], prefixes: List[str],
              ignores: list, whole_tree: bool) -> Report:
    listed = diffscope.git_paths(["ls-files", "--", *pages_globs])
    if listed is None:
        return Report([], 0, 0, 0, True)
    pages = sorted(p for p in listed if p and not diffscope.ignored(p, ignores))

    added: Optional[Dict[str, Set[int]]] = None
    if not whole_tree:
        if not base_ref:
            return Report([], 0, 0, 0, True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, True)
        diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                                  base.strip()])
        if diff is None:
            return Report([], 0, 0, 0, True)
        new, deleted = diffscope.parse_diff(diff)
        added = {rel: {n for n, text in numbered.items()
                       if text.strip() and text not in deleted}
                 for rel, numbered in new.items()}

    corpus = Corpus(div_re(prefixes), ignores)
    findings: Dict[Tuple[str, int], Finding] = {}
    reached: Set[str] = set()
    for page in pages:
        tree = corpus.reach(page)
        for path, includes in tree.items():
            reached.add(path)
            lines = corpus.lines[path]
            keep = None if added is None else added.get(path, set())
            for line, div_id in corpus.scans[path].divs:
                if keep is not None and line not in keep:
                    continue
                if exempt(lines, line):
                    continue
                findings.setdefault((path, line), Finding(path, line, page, "#" + div_id))
            if keep is None:
                continue  # whole tree: the divs themselves are reported
            for line, target, child in includes:
                if line not in keep or child is None or exempt(lines, line):
                    continue
                if corpus.holds_exposition(child, page, set()):
                    findings.setdefault((path, line), Finding(path, line, page, target))
    divs = sum(len(corpus.scans[p].divs) for p in reached)
    ordered = sorted(findings.values(), key=lambda f: (f.path, f.line))
    return Report(ordered, len(pages), len(reached), divs, False)


def format_message(f: Finding) -> str:
    if f.what.startswith("#"):
        thing = f"the exposition div {f.what}"
    else:
        thing = f"an include of {f.what}, which holds exposition divs,"
    return (
        f"Lab page {f.page} gains {thing}. A lab applies what the exposition "
        "pages teach, so move the definition or result to the exposition page "
        "for its topic and link it from the lab (psw: Keep expository content "
        "out of labs), or add <!-- lab-exposition-ok: reason -->."
    )


def main() -> int:
    base_ref = os.environ.get("CLE_BASE_REF", "").strip()
    pages = os.environ.get("CLE_PAGES", DEFAULT_PAGES).split() or DEFAULT_PAGES.split()
    prefixes = (os.environ.get("CLE_PREFIXES", DEFAULT_PREFIXES).split()
                or DEFAULT_PREFIXES.split())
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("CLE_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("CLE_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("CLE_WHOLE_TREE", False)

    report = run_check(base_ref, pages, prefixes, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the lab-exposition check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every lab that already carries exposition)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.pages} lab page(s), reaching {report.files} file(s) "
        f"and {report.divs} exposition div(s) (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for f in report.findings:
        print(f"::{severity} file={f.path},line={f.line}::{format_message(f)}")
    if not report.findings:
        print("No lab page gains a definition or result div.")
        return 0
    print(f"\n{len(report.findings)} exposition item(s) in lab pages.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
