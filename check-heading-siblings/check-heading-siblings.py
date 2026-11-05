#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a heading that a pull request adds to a group of too many sibling headings.

Sibling headings are headings of the same level under the same parent heading
(the top-level headings of a page are siblings under the page). A reader who
scans a list of headings holds the whole list in mind while choosing among
them, so the lab's guideline is to aim for at most about five and to split or
group when there are more than seven (Ezra, 2026-11-02; psw
``chapters/teaching.qmd``, "Keep sibling headings to about five"). The
threshold here is the seven at which the guideline says to act, not the five
it says to aim for, so the check does not fire on a page that merely sits
between the two.

The check measures the *expanded* page: the page's own text with every
``{{< include >}}`` shortcode replaced by the file it names, since a chapter's
headings are often split across subfiles. Headings inside fenced code blocks
and HTML comments do not count.

What is flagged: a group of more than ``CHS_MAX`` sibling headings, when the
diff adds one of its headings, in the page or in a file it includes. The
finding sits on the first added heading of the group.

Also flagged: a page whose top level holds a single heading (fewer than
``CHS_MIN``, default 2) when the diff adds that heading. The table of contents
then has one entry, which usually restates the page title above about a
hundred included files (lds#1893). The top level is the shallowest level with
no parent heading; a page with no headings is not flagged.

What is not flagged: a group the diff did not add a heading to, and a page
carrying ``<!-- check-heading-siblings: allow -->`` anywhere in its own file.

Design notes, in the model of ``check-page-length``:

- **Diff-scoped by default.** Existing crowded pages are not reflagged until an
  edit adds a heading to them; nothing is swept.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``CHS_WHOLE_TREE=true`` scans
  every page, to measure a corpus.
- **Fails by default** (``CHS_FAIL`` defaults to true).

Configuration (environment variables, set by the composite action):
  CHS_BASE_REF      Git ref/SHA to diff against.
  CHS_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  CHS_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  CHS_FAIL          "true" => exit 1 on a finding; default "true" (set "false" to warn only).
  CHS_WHOLE_TREE    "true" => scan every tracked matching page in full.
  CHS_MAX           Largest number of sibling headings (default 7).
  CHS_MIN           Fewest top-level headings a page with any may have (default 2).
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
DEFAULT_MAX = 7
DEFAULT_MIN = 2
ALLOW_MARKER = "check-heading-siblings: allow"

INCLUDE_RE = re.compile(r"\{\{<\s*include\s+(\S+?)\s*>\}\}")
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(\S.*?)[ \t]*#*[ \t]*$")
TITLE_RE = re.compile(r"^title:", re.MULTILINE)
CALLOUT_RE = re.compile(r"^[ \t]*:::+[ \t]*\{[^}]*\.callout")
UNNUMBERED_RE = re.compile(r"\{[^}]*\.unnumbered[^}]*\}")
ATTR_RE = re.compile(r"[ \t]*\{[^}]*\}[ \t]*$")


class Source(NamedTuple):
    """One line of the expanded page and where it came from."""
    path: str
    line: int
    text: str


class Heading(NamedTuple):
    level: int
    title: str
    parent: int
    path: str
    line: int


class Finding(NamedTuple):
    path: str
    line: int
    level: int
    parent: str
    count: int
    limit: int
    lone: bool = False


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


def expand(path: str, root: str, seen: Tuple[str, ...] = ()) -> List[Source]:
    """The page's lines with includes inlined, each with its origin."""
    real = os.path.realpath(path)
    text = read_text(path)
    if text is None or real in seen:
        return []
    out: List[Source] = []
    for number, line in enumerate(text.split("\n"), start=1):
        m = INCLUDE_RE.search(line)
        target = resolve_include(m.group(1), path, root) if m else None
        if target:
            out.extend(expand(target, root, seen + (real,)))
        else:
            out.append(Source(os.path.normpath(path), number, line))
    return out


def headings(lines: List[Source]) -> List[Heading]:
    """Headings outside fenced code and HTML comments, each with its parent.

    The parent is the nearest earlier heading of a lower level, as an index
    into the returned list, or -1 for the page itself.
    """
    found: List[Heading] = []
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    prev_line = ""
    in_front_matter: Dict[str, bool] = {}
    for src in lines:
        line = src.text
        if src.line == 1 and line.strip() == "---":
            in_front_matter[src.path] = True
            continue
        if in_front_matter.get(src.path):
            if line.strip() in ("---", "..."):
                in_front_matter[src.path] = False
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        m = FENCE_RE.match(line)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if line.lstrip().startswith("<!--") and "-->" not in line:
            in_comment = True
            continue
        previous, prev_line = prev_line, (line if line.strip() else prev_line)
        h = HEADING_RE.match(line)
        if not h:
            continue
        # A callout's title and an unnumbered heading are not outline entries.
        if CALLOUT_RE.match(previous) or UNNUMBERED_RE.search(h.group(2)):
            continue
        level = len(h.group(1))
        parent = -1
        for index in range(len(found) - 1, -1, -1):
            if found[index].level < level:
                parent = index
                break
        title = ATTR_RE.sub("", h.group(2)).strip()
        found.append(Heading(level, title, parent, src.path, src.line))
    return found


def crowded_groups(found: List[Heading], limit: int
                   ) -> List[Tuple[int, List[Heading]]]:
    """Groups of siblings over ``limit``, as (parent index, members)."""
    groups: Dict[Tuple[int, int], List[Heading]] = {}
    for h in found:
        groups.setdefault((h.level, h.parent), []).append(h)
    return [(parent, members) for (_, parent), members in groups.items()
            if len(members) > limit]


def lone_top_heading(found: List[Heading], minimum: int) -> Optional[Heading]:
    """The page's only top-level heading when there are fewer than ``minimum``.

    The top level is the shallowest level that has no parent heading. A page
    with no headings has none to flag.
    """
    top = [h for h in found if h.parent == -1]
    if not top:
        return None
    shallowest = min(h.level for h in top)
    group = [h for h in top if h.level == shallowest]
    return group[0] if len(group) < minimum else None


def format_message(f: Finding) -> str:
    if f.lone:
        return (f"This is the only top-level heading of the page, so the "
                f"table of contents has a single entry that duplicates or "
                f"restates the page title. Fix: add the sections the page "
                f"already contains as sibling headings (about five), or drop "
                f"the heading if the page has just one section; move content, "
                f"do not delete it")
    where = (f"under '{f.parent}'" if f.parent else "at the top level of the page")
    return (f"This heading is one of {f.count} level-{f.level} sibling headings "
            f"{where}, over the limit of {f.limit}. A reader scanning the "
            f"headings holds them all in mind at once, so aim for about five. "
            f"Fix: group related headings under a new parent heading that "
            f"names what they share, or split the page into several pages; "
            f"move content, do not delete it")


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
    findings: List[Finding]
    pages: int
    skipped: bool


def scan_page(path: str, root: str, touched: Optional[Dict[str, List[int]]],
              limit: int, minimum: int = 0) -> List[Finding]:
    """Findings for the crowded groups of ``path`` the diff added a heading to.

    ``touched`` maps a file to its added lines; None means scan regardless
    (whole-tree), reporting on the first heading of each crowded group.
    """
    if ALLOW_MARKER in (read_text(path) or ""):
        return []
    found = headings(expand(path, root))
    findings: List[Finding] = []
    for parent, members in crowded_groups(found, limit):
        if touched is None:
            anchor = members[0]
        else:
            added = [h for h in members if h.line in touched.get(h.path, ())]
            if not added:
                continue
            anchor = added[0]
        parent_title = found[parent].title if parent >= 0 else ""
        findings.append(Finding(anchor.path, anchor.line, anchor.level,
                                parent_title, len(members), limit))
    lone = lone_top_heading(found, minimum)
    if lone is not None and (touched is None
                             or lone.line in touched.get(lone.path, ())):
        findings.append(Finding(lone.path, lone.line, lone.level, "", 1,
                                limit, lone=True))
    return findings


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool, limit: int, minimum: int = 0) -> Report:
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
    findings: List[Finding] = []
    seen: Set[Tuple[str, int]] = set()
    pages = 0
    for rel in sorted(candidates):
        if _ignored(rel, ignores):
            continue
        text = read_text(rel)
        if text is None or not is_page(text):
            continue
        pages += 1
        for f in scan_page(rel, root, touched, limit, minimum):
            if (f.path, f.line) not in seen:
                seen.add((f.path, f.line))
                findings.append(f)
    return Report(findings, pages, False)


def main() -> int:
    base_ref = os.environ.get("CHS_BASE_REF", "").strip()
    globs = os.environ.get("CHS_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("CHS_PATHS_IGNORE", "")))
    fail = _env_flag("CHS_FAIL", True)
    whole_tree = _env_flag("CHS_WHOLE_TREE", False)
    limit = _env_int("CHS_MAX", DEFAULT_MAX)

    minimum = _env_int("CHS_MIN", DEFAULT_MIN)

    report = run_check(base_ref, globs, ignores, whole_tree, limit, minimum)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the sibling-heading check for this run ({reason}; "
              f"not falling back to a whole-tree scan, which would reflag "
              f"every crowded page the corpus already carries).")
        return 0
    scope = "whole tree" if whole_tree else f"pages touched since {base_ref}"
    print(f"Measured {report.pages} page(s) (scope: {scope}; limit: "
          f"{limit} sibling headings).")
    severity = "error" if fail else "warning"
    for f in report.findings:
        print(f"::{severity} file={f.path},line={f.line}::{format_message(f)}")
    if not report.findings:
        print("No touched heading group is over the limit.")
        return 0
    print(f"\n{len(report.findings)} heading group(s) are over the limit.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
