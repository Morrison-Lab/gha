#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a remark div that states a result.

The lab's rule (Ezra, 2026-11-07; psw ``chapters/teaching.qmd``, psw#512): a
remark (``#rem-``) holds commentary. A statement of what is true, such as an
equation with its conditions, belongs in a theorem-type div (``#thm-``,
``#lem-``, ``#cor-`` or ``#prp-``) with its proof. Split the result from the
commentary.

The check reads every ``#rem-`` div and flags it when it both

- displays an equation (``$$...$$``, ``align`` or ``\ba ... \ea``), and
- states a claim in its prose: "equals", "is at least", "is at most", "never",
  "exactly when", "if and only if", "for every", "for all", "holds",
  "satisfies".

It is a heuristic and warn-only by default: commentary can mention a display
without asserting it, and the check cannot tell. ``<!-- check-results-in-remarks:
allow -->`` in the div exempts it. The check promotes to failing (``fail:
true``) after several pull requests show no false positive (gha#1571).

A div is checked when the diff adds a line inside it, or always with
``RIR_WHOLE_TREE=true``. No base-ref means the run is skipped.

Configuration (environment variables, set by the composite action):
  RIR_BASE_REF      Git ref/SHA to diff against; empty and not whole-tree => skip.
  RIR_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  RIR_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  RIR_FAIL          "true" => blocking; default "false" (warning annotations).
  RIR_WHOLE_TREE    "true" => check every remark in the tree.
"""

import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

_ENGINE_PATH = Path(__file__).resolve().parent.parent / "check-write-idiom" / "check-write-idiom.py"
_spec = importlib.util.spec_from_file_location("check_write_idiom_engine", _ENGINE_PATH)
assert _spec is not None and _spec.loader is not None
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)

# The div reader and the git plumbing are check-definition-equations', so the
# two checks cannot drift apart on fences, nested divs or the diff model.
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
    "state the result in its own #thm-, #lem-, #cor- or #prp- div with its "
    "proof, keep only the commentary in the remark, or add "
    "<!-- check-results-in-remarks: allow --> to the remark"
)

ID_RE = re.compile(r"#(rem-[A-Za-z0-9_-]+)")
ALLOW_RE = re.compile(r"<!--\s*check-results-in-remarks:\s*allow\s*-->", re.IGNORECASE)
CLAIM_RE = re.compile(
    r"\b(?:equals?|is\s+at\s+least|is\s+at\s+most|never|exactly\s+when|"
    r"if\s+and\s+only\s+if|iff|for\s+(?:every|all)|holds?|satisf(?:y|ies))\b",
    re.IGNORECASE)


class Finding(NamedTuple):
    path: str
    line: int
    message: str


def find_divs(lines: List[str]):
    """Outermost divs with a ``rem-`` id, outside code fences."""
    saved = base.ID_RE
    base.ID_RE = ID_RE
    try:
        return base.find_divs(lines)
    finally:
        base.ID_RE = saved


def reasons(div) -> List[str]:
    """Why a remark states a result; empty when it is commentary or exempt."""
    if any(ALLOW_RE.search(line) for line in div.body):
        return []
    text = base.strip_fences(div.body)
    if not base.displays(text):
        return []
    prose = base.ALIGN_RE.sub(" ", base.BA_RE.sub(" ", base.DISPLAY_RE.sub(" ", text)))
    claim = CLAIM_RE.search(prose)
    if not claim:
        return []
    return [f'it displays an equation and says "{claim.group(0).lower()}"']


def check_file(path: str, lines: List[str],
               touched: Optional[Set[int]]) -> List[Finding]:
    findings: List[Finding] = []
    for d in find_divs(lines):
        if touched is not None and not any(n + 1 in touched
                                           for n in range(d.start, d.end + 1)):
            continue
        why = reasons(d)
        if why:
            findings.append(Finding(path, d.start + 1,
                f"#{d.ident}: {'; '.join(why)} (heuristic). A remark holds "
                f"commentary; a statement of what is true belongs in a "
                f"theorem-type div. Fix: {ADVICE}"))
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
    base_ref = os.environ.get("RIR_BASE_REF", "").strip()
    globs = os.environ.get("RIR_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = base.compile_ignores(base._split_list(os.environ.get("RIR_PATHS_IGNORE", "")))
    fail = base._env_flag("RIR_FAIL", _DEFAULT_FAIL)
    whole_tree = base._env_flag("RIR_WHOLE_TREE", False)
    report = run_check(base_ref, globs, ignores, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(f"{'::warning::' if base_ref else ''}Skipping the results-in-remarks "
              f"check for this run ({reason}; not falling back to a whole-tree scan).")
        return 0
    for f in report.findings:
        print(f"::{'error' if fail else 'warning'} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("No touched remark states a result.")
        return 0
    print(f"\n{len(report.findings)} remark(s) that state a result.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
