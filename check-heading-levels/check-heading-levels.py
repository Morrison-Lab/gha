#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a heading whose level breaks the page's outline.

The lab's rule (Ezra, 2026-10-30, after pages split out of larger pages kept
headings from the page they came from; corrected 2026-11-02): a page's title
comes from its front matter and is not a numbered level, so the body starts
at level 1 (``#``) and each heading is at most one level deeper than the one
before it. A body that starts at level 2 numbers its sections 0.1, 0.2 under
``number-sections: true``. Four mistakes are flagged:

- **Skipped level.** A heading more than one level deeper than the heading
  before it in the same file (``#`` then ``###``). The first heading of a
  page is compared with the title, level 0; the first heading of an included
  subfile is not compared with anything.
- **Page starts too deep.** The first heading a page renders, following its
  ``{{< include >}}`` shortcodes, is deeper than level 1 (a shared
  ``### Configuring R`` include that opens ten chapters, or a body of ``##``
  sections that number 0.1, 0.2).
- **Section numbered 0.x.** A numbered heading below level 1 that comes
  before any numbered level-1 heading, when the page's first heading is an
  unnumbered ``# Overview {.unnumbered}``: Quarto numbers it 0.1 all the
  same (Ezra, 2026-11-10: "so no section number starts with `0.`").
- **Title repeated as a heading.** The first heading a page renders repeats
  the page's ``title:`` (a section copied into its own page with its
  ``# Newton's method`` heading still on it).

What is not counted: headings inside code fences, HTML comments, YAML front
matter or any fenced div (``####`` titles of definition and exercise divs are
the lab's convention); a line carrying ``<!-- check-heading-levels: allow
-->``.

Design notes, in the model of ``check-one-div-per-subfile``:

- **Diff-scoped by default.** A finding is reported only when the heading
  line that causes it was added. The whole page and its includes are parsed,
  since the first heading may sit in a file the diff did not touch.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``HLV_WHOLE_TREE=true`` scans the
  whole tree, which measures how many headings the corpus carries.
- **Failing by default** (``HLV_FAIL`` defaults to true; Ezra, 2026-11-02:
  agents ignore warnings). Diff-scoped, so only added headings can fail.

Configuration (environment variables, set by the composite action):
  HLV_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  HLV_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  HLV_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  HLV_FAIL          "false" => warn only; default "true".
  HLV_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import functools
import importlib.util
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


def _load_sibling(name: str):
    """Import a sibling check's script, whose directory name has hyphens."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, os.pardir, name, name + ".py")
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ods = _load_sibling("check-one-div-per-subfile")

# The git and file helpers come from check-common (gha#1856);
# the div and fence parsing still comes from check-one-div-per-subfile.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = True
ALLOW_MARKER = "check-heading-levels: allow"

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(\S.*?)(?:[ \t]+#+)?[ \t]*$")
INCLUDE_RE = re.compile(r"\{\{<\s*include\s+(\S+?)\s*>\}\}")
TITLE_RE = re.compile(r"""^title:\s*(?:"(.*)"|'(.*)'|(.*?))\s*$""")
BLOCK_SCALAR_RE = re.compile(r"^[>|][+-]?\d*$")
ATTR_RE = re.compile(r"\s*\{[^{}]*\}\s*$")

ADVICE_SKIP = "use the next level down, or add the missing level"
ADVICE_DEEP = (
    "start the page at level 1: raise this heading, or the include's other "
    "headings with it"
)
ADVICE_ZERO = (
    "add a numbered level-1 heading above it, or raise it to level 1"
)
# ``{.unnumbered}`` or ``{-}`` among a heading's trailing attributes.
UNNUMBERED_RE = re.compile(
    r"\{[^{}]*(?:(?<![\w-])\.unnumbered(?![\w-])|(?<![^\s{])-(?![^\s}]))[^{}]*\}\s*$")
ADVICE_TITLE = (
    "drop the heading (the title already names the page) and raise its "
    "subsections one level, or add <!-- check-heading-levels: allow -->"
)


class Heading(NamedTuple):
    level: int
    text: str
    path: str
    line: int
    allowed: bool


class Finding(NamedTuple):
    path: str
    line: int
    kind: str
    message: str


def is_page(path: str) -> bool:
    """A page is a ``.qmd`` file with a ``title:`` in its front matter.

    A file without one is an include, whatever its name: it takes its level
    from the page that includes it, so its first heading is not compared
    with the title.
    """
    name = os.path.basename(path)
    if not name.endswith(".qmd") or name.startswith("_"):
        return False
    return page_title(read_lines(path) or []) is not None


def clean_text(text: str) -> str:
    """Heading or title text without its ``{#id .class}`` attributes."""
    return ATTR_RE.sub("", text).strip().strip("\"'").lower()


@functools.lru_cache(maxsize=None)
def _read_cached(path: str, mtime_ns: int, size: int) -> Optional[Tuple[str, ...]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return None
    if lines and lines[-1] == "":
        lines.pop()
    return tuple(lines)


def read_lines(path: str) -> Optional[List[str]]:
    """The file's lines, read once per version of the file.

    Every page that includes a shared subfile parses it again, so the read is
    cached on the file's modification time and size.
    """
    try:
        info = os.stat(path)
    except OSError:
        return None
    cached = _read_cached(path, info.st_mtime_ns, info.st_size)
    return None if cached is None else list(cached)


def is_unnumbered(text: str) -> bool:
    """Whether a heading's attributes drop it from the section numbering."""
    return bool(UNNUMBERED_RE.search(text))


NUMBER_OFF_RE = re.compile(r"^number-sections:\s*(?:false|no)\s*(?:#.*)?$")


def numbering_off(lines: List[str]) -> bool:
    """Whether the front matter sets ``number-sections: false`` at its top
    level, so the page numbers no section at all."""
    if not lines or lines[0].strip() != "---":
        return False
    for raw in lines[1:]:
        if raw.strip() in ("---", "..."):
            return False
        if NUMBER_OFF_RE.match(raw):
            return True
    return False


def page_title(lines: List[str]) -> Optional[str]:
    """The ``title:`` of the YAML front matter, or None."""
    if not lines or lines[0].strip() != "---":
        return None
    for idx, raw in enumerate(lines[1:], start=1):
        if raw.strip() in ("---", "..."):
            return None
        m = TITLE_RE.match(raw)
        if m:
            value = next(g for g in m.groups() if g is not None)
            if BLOCK_SCALAR_RE.match(value):
                return " ".join(_block_scalar(lines, idx))
            return value
    return None


def _block_scalar(lines: List[str], idx: int) -> List[str]:
    """The indented lines under ``title: >-`` (a folded or literal title)."""
    body: List[str] = []
    for raw in lines[idx + 1:]:
        if raw.strip() and not raw[0].isspace():
            break
        if raw.strip():
            body.append(raw.strip())
    return body


def resolve_include(target: str, current: str, root: str) -> Optional[str]:
    """Find an include's file: beside the includer, at the root, or minus a
    leading repository directory (``mds/_subfiles/x.qmd`` in a host site)."""
    candidates = [os.path.join(os.path.dirname(current), target),
                  os.path.join(root, target)]
    if "/" in target:
        candidates.append(os.path.join(root, target.split("/", 1)[1]))
    for cand in candidates:
        if os.path.isfile(cand):
            return os.path.realpath(cand)
    return None


def scan_headings(path: str, root: str, seen: Tuple[str, ...] = ()
                  ) -> List[Tuple[Heading, bool]]:
    """Headings in the order the page renders them, following includes.

    Each is paired with whether it sits in ``path`` itself (not an include).
    The skip rule in ``scan_subfile`` compares headings of one file only;
    ``scan_page`` compares every heading the page renders, includes too, so
    an include that opens a level too deep also breaks the next heading.
    ``seen`` holds the real paths of the files being expanded, so a cycle,
    including one back to the top-level page, stops.
    """
    lines = read_lines(path)
    if lines is None:
        return []
    real = os.path.realpath(path)
    out: List[Tuple[Heading, bool]] = []
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    in_yaml = bool(lines) and lines[0].strip() == "---"
    depth = 0
    for idx, original in enumerate(lines):
        if in_yaml:
            if idx > 0 and original.strip() in ("---", "..."):
                in_yaml = False
            continue
        raw = original
        if fence is None:
            raw, in_comment = ods.strip_comments(raw, in_comment)
        m = ods.FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        dm = ods.DIV_RE.match(raw)
        if dm:
            depth = depth + 1 if dm.group(2) else max(0, depth - 1)
            continue
        inc = INCLUDE_RE.search(raw)
        if inc:
            target = resolve_include(inc.group(1), path, root)
            if depth == 0 and target and target != real and target not in seen:
                out.extend((h, False) for h, _ in
                           scan_headings(target, root, seen + (real,)))
            continue
        hm = HEADING_RE.match(raw)
        if hm and depth == 0:
            out.append((Heading(len(hm.group(1)), hm.group(2), path, idx + 1,
                                ALLOW_MARKER in original), True))
    return out


def scan_page(path: str, root: str) -> List[Finding]:
    """Every finding for one page, with the source line that causes it."""
    headings = scan_headings(path, root)
    lines = read_lines(path) or []
    title = page_title(lines)
    findings: List[Finding] = []
    if headings:
        first = headings[0][0]
        if first.level > 1 and not first.allowed:
            findings.append(Finding(
                first.path, first.line, "deep",
                f"Page starts at level {first.level} ('{first.text}'); the "
                f"title is not a numbered level, so the first heading is "
                f"level 1 (a level 2 start numbers sections 0.1, 0.2). "
                f"Fix: {ADVICE_DEEP}"))
        elif (title and first.level == 1 and not first.allowed
              and clean_text(first.text) == clean_text(title)):
            findings.append(Finding(
                first.path, first.line, "title",
                f"The page's first heading ('{first.text}') repeats its "
                f"title. Fix: {ADVICE_TITLE}"))
    for heading, _own in ([] if numbering_off(lines) else headings):
        if is_unnumbered(heading.text):
            continue
        if heading.level == 1:
            break
        if heading is not headings[0][0] and not heading.allowed:
            findings.append(Finding(
                heading.path, heading.line, "zero",
                f"Heading '{heading.text}' is numbered 0.x: no numbered "
                f"level-1 heading comes before it. Fix: {ADVICE_ZERO}"))
        break
    prev = 0
    for heading, own in headings:
        reported_deep = (heading is headings[0][0] and heading.level > 1)
        if (own and heading.level > prev + 1 and not heading.allowed
                and not reported_deep):
            findings.append(Finding(
                heading.path, heading.line, "skip",
                f"Heading '{heading.text}' is level {heading.level} after "
                f"level {prev}, skipping a level. Fix: {ADVICE_SKIP}"))
        prev = heading.level
    return findings


def scan_subfile(path: str) -> List[Finding]:
    """Skipped levels in an include, whose first heading has no predecessor."""
    findings: List[Finding] = []
    prev: Optional[int] = None
    for heading, own in scan_headings(path, os.getcwd()):
        if not own:
            continue
        if prev is not None and heading.level > prev + 1 and not heading.allowed:
            findings.append(Finding(
                heading.path, heading.line, "skip",
                f"Heading '{heading.text}' is level {heading.level} after "
                f"level {prev}, skipping a level. Fix: {ADVICE_SKIP}"))
        prev = heading.level
    return findings


class Report(NamedTuple):
    findings: List[Finding]
    files: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Report findings whose heading line was added since ``base_ref``."""
    root = os.getcwd()
    listing = diffscope.run_git(["ls-files", "--", *globs])
    if listing is None:
        return Report([], 0, True)
    files = [f for f in listing.splitlines()
             if f and not diffscope.ignored(f, ignores)]
    keep: Dict[str, Set[int]] = {}
    if not whole_tree:
        if not base_ref:
            return Report([], 0, True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, True)
        diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                             base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, True)
        added, _deleted = diffscope.parse_diff(diff)
        for rel, numbered in added.items():
            keep[rel] = {n for n, text in numbered.items() if text.strip()}
    found: List[Finding] = []
    for rel in sorted(files):
        if is_page(rel):
            found.extend(scan_page(rel, root))
        else:
            found.extend(scan_subfile(rel))
    seen: Set[Tuple[str, int, str]] = set()
    kept: List[Finding] = []
    for f in found:
        rel = os.path.relpath(f.path, root)
        key = (rel, f.line, f.kind)
        if key in seen or diffscope.ignored(rel, ignores):
            continue
        if not whole_tree and f.line not in keep.get(rel, set()):
            continue
        seen.add(key)
        kept.append(Finding(rel, f.line, f.kind, f.message))
    return Report(kept, len(files), False)


def main() -> int:
    base_ref = os.environ.get("HLV_BASE_REF", "").strip()
    globs = os.environ.get("HLV_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("HLV_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("HLV_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("HLV_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the heading-level check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every heading the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.files} file(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for f in report.findings:
        print(f"::{severity} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("No heading breaks its page's outline.")
        return 0
    print(f"\n{len(report.findings)} heading(s) breaking a page's outline.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
