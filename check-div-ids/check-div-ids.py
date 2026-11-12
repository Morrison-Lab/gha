#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a theorem-type fenced div that lacks the id its class needs.

Quarto and the lab's ``callouty-theorem`` and ``custom-callout`` extensions
build a callout, a number and a cross-reference target from a div's id. A div
written ``::: {.remark}`` with no ``#rem-`` id renders as a plain block quote,
with no callout box and no number (Morrison-Lab/lds#1600, the Hoeffding
source note on the big-ideas page).

What is flagged: a fenced div whose attributes hold one of these classes but
no id with the matching prefix, when the diff adds the opening line.

- ``.definition`` needs ``#def-``
- ``.theorem`` needs ``#thm-``
- ``.lemma`` needs ``#lem-``
- ``.corollary`` needs ``#cor-``
- ``.proposition`` needs ``#prp-``
- ``.remark`` needs ``#rem-``
- ``.example`` needs ``#exm-``
- ``.exercise`` needs ``#exr-``

What is not flagged: a div with the right id (any other classes, such as
``.notes``, are fine); a div without a theorem-type class; fences inside code
blocks, HTML comments and blockquotes; and any div the diff did not add.

Design notes, in the model of ``check-one-div-per-subfile``:

- **Diff-scoped by default.** Only a div opener added since ``CDI_BASE_REF``
  is reported. An added line whose exact text was also deleted in the same
  diff is treated as moved, not new.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``CDI_WHOLE_TREE=true`` asks for
  the whole tree explicitly.
- **Fails by default** (``CDI_FAIL`` defaults to true).

Configuration (environment variables, set by the composite action):
  CDI_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  CDI_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  CDI_PATHS_IGNORE  Comma/newline-separated glob patterns (relative paths) to
                    skip. Supports ``*``, ``?`` and recursive ``**``.
  CDI_FAIL          "true" => exit 1 on a finding; default "true".
  CDI_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402
import mdmask  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = True

PREFIX_FOR_CLASS = {
    "definition": "def",
    "theorem": "thm",
    "lemma": "lem",
    "corollary": "cor",
    "proposition": "prp",
    "remark": "rem",
    "example": "exm",
    "exercise": "exr",
}

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
QUOTED_RE = re.compile(r'"[^"]*"|\'[^\']*\'')
CLASS_RE = re.compile(r"(?:^|[\s{])\.([A-Za-z][\w-]*)(?=[\s}.#]|$)")
ID_RE = re.compile(r"(?:^|[\s{])#([A-Za-z][\w-]*)(?=[\s}.#]|$)")


class Finding(NamedTuple):
    line: int
    cls: str
    prefix: str


def missing_prefix(attrs: str) -> Optional[Tuple[str, str]]:
    """The (class, prefix) a div needs but lacks, or None."""
    bare = QUOTED_RE.sub('""', attrs)
    ids = ID_RE.findall(bare)
    for cls in CLASS_RE.findall(bare):
        prefix = PREFIX_FOR_CLASS.get(cls)
        if prefix and not any(i.startswith(prefix + "-") for i in ids):
            return cls, prefix
    return None


def drop_comments(text: str, in_comment: bool) -> Tuple[str, bool]:
    """Remove HTML comment text from one line; say whether one stays open."""
    if in_comment:
        end = text.find("-->")
        if end < 0:
            return "", True
        text = text[end + 3:]
    spans: List[str] = []
    text = mdmask.CODE_SPAN_RE.sub(lambda m: spans.append(m.group(0)) or "\0", text)
    while True:
        start = text.find("<!--")
        end = text.find("-->", start + 4) if start >= 0 else -1
        if end < 0:
            break
        text = text[:start] + text[end + 3:]
    start = text.find("<!--")
    opened = start >= 0
    if opened:
        text = text[:start]
    it = iter(spans)
    return re.sub("\0", lambda _: next(it), text), opened


def scan(lines: List[str]) -> Tuple[List[Finding], int]:
    """Div openers that lack their id, and the divs examined."""
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    found: List[Finding] = []
    seen = 0
    for idx, raw in enumerate(lines):
        if fence is None:
            raw, in_comment = drop_comments(raw, in_comment)
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        dm = DIV_RE.match(raw)
        if not dm or not dm.group(2):
            continue
        seen += 1
        need = missing_prefix(dm.group(2))
        if need:
            found.append(Finding(idx + 1, need[0], need[1]))
    return found, seen


def format_message(f: Finding) -> str:
    return (f"This div has class .{f.cls} but no #{f.prefix}- id, so it "
            f"renders as a plain block quote with no callout or number. "
            f"Fix: give it an id such as #{f.prefix}-<name> and a #### title")


compile_ignores = diffscope.compile_ignores


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    divs: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Scan div openers added since ``base_ref``, or all when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
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
        diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                                  base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, True)
        added, deleted = diffscope.parse_diff(diff)
        for rel, numbered in added.items():
            if diffscope.ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, Finding]] = []
    files = divs = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        found, seen = scan(content)
        divs += seen
        keep = wanted[rel]
        for f in found:
            if keep is None or f.line in keep:
                findings.append((rel, f))
    return Report(findings, files, divs, False)


def main() -> int:
    base_ref = os.environ.get("CDI_BASE_REF", "").strip()
    globs = os.environ.get("CDI_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(
        diffscope.split_list(os.environ.get("CDI_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("CDI_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("CDI_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the div-ids check for this run ({reason}; not "
            f"falling back to a whole-tree scan, which would reflag every div "
            f"the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.divs} div(s) across {report.files} file(s) "
          f"(scope: {scope}).")
    severity = "error" if fail else "warning"
    for rel, f in report.findings:
        print(f"::{severity} file={rel},line={f.line}::{format_message(f)}")
    if not report.findings:
        print("Every theorem-type div has its id.")
        return 0
    print(f"\n{len(report.findings)} div(s) lack the id their class needs.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
