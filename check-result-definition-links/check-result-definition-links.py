#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a result div that links no definition.

The lab's rule (Ezra, 2026-11-09): every result div (``#thm-``, ``#lem-``,
``#cor-`` or ``#prp-``) links at least one definition, so a reader can reach
the meaning of the terms the result uses. A definition link is a cross-reference
``@def-id`` or a Markdown link whose target ends in ``#def-id`` (this site or a
prerequisite one).

A result with no defined term to link (a pure identity between numbers, say) is
exempted with ``<!-- check-result-definition-links: allow -->`` in the div,
with the reason after it. The check is warn-only by default.

A div is checked when the diff adds a line inside it, or always with
``CRDL_WHOLE_TREE=true``. No base-ref means the run is skipped.

Configuration (environment variables, set by the composite action):
  CRDL_BASE_REF      Git ref/SHA to diff against; empty and not whole-tree => skip.
  CRDL_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  CRDL_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  CRDL_FAIL          "true" => blocking; default "false" (warning annotations).
  CRDL_WHOLE_TREE    "true" => check every result div in the tree.
"""

import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set

_ENGINE_PATH = Path(__file__).resolve().parent.parent / "check-write-idiom" / "check-write-idiom.py"
_spec = importlib.util.spec_from_file_location("check_write_idiom_engine", _ENGINE_PATH)
assert _spec is not None and _spec.loader is not None
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)

# The div reader and the git plumbing are check-definition-equations', so the
# checks cannot drift apart on fences, nested divs or the diff model.
_DE_PATH = Path(__file__).resolve().parent.parent / "check-definition-equations" / "check-definition-equations.py"
_de_spec = importlib.util.spec_from_file_location("check_definition_equations_base", _DE_PATH)
assert _de_spec is not None and _de_spec.loader is not None
base = importlib.util.module_from_spec(_de_spec)
_de_spec.loader.exec_module(base)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = False

ADVICE = (
    "link the defined terms the result uses to their definitions, as @def-... "
    "or [term](page.qmd#def-...), or add "
    "<!-- check-result-definition-links: allow --> with the reason"
)

ID_RE = re.compile(r"#((?:thm|lem|cor|prp)-[A-Za-z0-9_-]+)")
ALLOW_RE = re.compile(r"<!--\s*check-result-definition-links:\s*allow\b", re.IGNORECASE)
# A definition link: a cross-reference `@def-id` (also `[@def-id]`), or a
# Markdown link whose target ends in `#def-id`, on this site or a prerequisite one.
DEF_REF_RE = re.compile(r"(?<![\w/.#-])@def-[A-Za-z0-9_-]+")
DEF_LINK_RE = re.compile(r"\]\([^)\s]*#def-[A-Za-z0-9_-]+[^)]*\)")


class Finding(NamedTuple):
    path: str
    line: int
    message: str


def find_divs(lines: List[str]):
    """Outermost divs with a result id (thm, lem, cor, prp), outside code fences."""
    saved = base.ID_RE
    base.ID_RE = ID_RE
    try:
        return base.find_divs(lines)
    finally:
        base.ID_RE = saved


def has_definition_link(div) -> bool:
    """Whether the div links a definition outside comments and code fences."""
    text = base.COMMENT_RE.sub(" ", base.strip_fences(div.body))
    return bool(DEF_REF_RE.search(text) or DEF_LINK_RE.search(text))


def check_file(path: str, lines: List[str],
               touched: Optional[Set[int]]) -> List[Finding]:
    findings: List[Finding] = []
    for d in find_divs(lines):
        if touched is not None and not any(n + 1 in touched
                                           for n in range(d.start, d.end + 1)):
            continue
        if any(ALLOW_RE.search(line) for line in d.body) or has_definition_link(d):
            continue
        findings.append(Finding(path, d.start + 1,
            f"#{d.ident}: the result links no definition. Every result div "
            f"links the defined terms it uses. Fix: {ADVICE}"))
    return findings


class Report(NamedTuple):
    findings: List[Finding]
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    out = base._run_git(["ls-files", "--", *globs])
    if out is None:
        return Report([], True)
    names = [r for r in out.splitlines()
             if r and not any(g.match(r) for g in ignores)]
    touched: Optional[Dict[str, Set[int]]] = None
    if not whole_tree:
        if not base_ref:
            return Report([], True)
        merge_base = base._run_git(["merge-base", base_ref, "HEAD"])
        if merge_base is None or not merge_base.strip():
            return Report([], True)
        diff = base._run_git([*engine.GIT_DIFF_ARGS, merge_base.strip(), "--", *globs])
        if diff is None:
            return Report([], True)
        touched = base.parse_diff(diff)
    findings: List[Finding] = []
    for rel in names:
        if touched is not None and not touched.get(rel):
            continue
        content = base._read_lines(rel)
        if content is not None:
            findings.extend(check_file(rel, content,
                                       None if touched is None else touched[rel]))
    return Report(sorted(findings), False)


def main() -> int:
    base_ref = os.environ.get("CRDL_BASE_REF", "").strip()
    globs = os.environ.get("CRDL_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = base.compile_ignores(base._split_list(os.environ.get("CRDL_PATHS_IGNORE", "")))
    fail = base._env_flag("CRDL_FAIL", _DEFAULT_FAIL)
    whole_tree = base._env_flag("CRDL_WHOLE_TREE", False)
    report = run_check(base_ref, globs, ignores, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(f"{'::warning::' if base_ref else ''}Skipping the result-definition-links "
              f"check for this run ({reason}; not falling back to a whole-tree scan).")
        return 0
    for f in report.findings:
        print(f"::{'error' if fail else 'warning'} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("Every touched result div links a definition.")
        return 0
    print(f"\n{len(report.findings)} result div(s) with no definition link.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
