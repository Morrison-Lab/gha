#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a definition written as an explicit sum or integral where an expectation fits.

The lab's rule (Ezra, 2026-11-07; psw ``chapters/defining-terms.qmd``, psw#513):
write a definition with an expectation operator where one fits, so
``\E{\log \frac{1}{p(X)}}`` and not ``\sum_x p(x) \log \frac{1}{p(x)}``.

The check reads every ``#def-`` div and flags it when a display equation

- contains a sum (``\sum``) or an integral (``\int``) whose summand is a
  probability mass or density (``p(x)``, ``p_X(x)``, ``f(x)``, ``f_X(x)``,
  ``\Pr(...)``) times another factor, and
- the div holds no expectation operator (``\E``, ``\Exp``, ``\Expect``,
  ``\mathbb{E}``, ``\mathrm{E}`` or ``\operatorname{E}``).

It is a heuristic and warn-only by default, because whether an expectation
expresses the quantity needs judgement. It skips

- a display with a ``\frac{1}{n}`` or ``\frac{1}{N}`` factor, or a sum over a
  data index (``i = 1`` to ``n``), which is a sample average;
- a lone probability mass or density with nothing else in the summand, such as
  ``\sum_x p(x) = 1``, which is not weighting anything; and
- a div titled "Expectation" or "Expected value", which defines the operator itself.

``<!-- check-definition-expectation: allow -->`` in the div exempts it.

A div is checked when the diff adds a line inside it, or always with
``DX_WHOLE_TREE=true``. No base-ref means the run is skipped.

Configuration (environment variables, set by the composite action):
  DX_BASE_REF      Git ref/SHA to diff against; empty and not whole-tree => skip.
  DX_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  DX_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  DX_FAIL          "true" => blocking; default "false" (warning annotations).
  DX_WHOLE_TREE    "true" => check every definition div in the tree.
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
    "write the quantity as an expectation (\\E{...}) of a function of the "
    "random variable, or add <!-- check-definition-expectation: allow --> to "
    "the definition"
)

ALLOW_RE = re.compile(r"<!--\s*check-definition-expectation:\s*allow\s*-->", re.IGNORECASE)
SUM_RE = re.compile(r"\\(?:sum|int)(?![A-Za-z])")
# A probability mass or density: p(x), p_X(x), p_{X \mid Y}(x), f(x), f_X(x), \Pr(...).
PMF_RE = re.compile(
    r"(?<![A-Za-z\\])(?:[pf](?:_\{[^{}]*\}|_[A-Za-z0-9])?|\\Pr|\\Prob)\s*"
    r"(?:\([^()]*\)|\\left\([^()]*\\right\))")
EXPECTATION_RE = re.compile(
    r"\\(?:E|Exp|Expect|Ex)(?![A-Za-z])|\\mathbb\{E\}|\\mathrm\{E\}|\\operatorname\{E\}")
SAMPLE_AVERAGE_RE = re.compile(
    r"\\frac\{1\}\{\s*[nN]\s*\}|\\sum\s*_\{?\s*[a-z]\s*=\s*1\s*\}?\s*\^\{?\s*[nN]\b")
TITLE_ATTR_RE = re.compile(r"""title\s*=\s*(?:"([^"]*)"|'([^']*)')""")
OPERATOR_TITLE_RE = re.compile(r"\bexpect(?:ation|ed\s+value)\b", re.IGNORECASE)
LEFTOVER_RE = re.compile(r"[A-Za-z]")
# What carries no weighted factor: spacing, the differential, scripts and bounds.
FILLER_RE = re.compile(
    r"\\[,;:!]|\\mathrm\{d\}\s*[A-Za-z]|\\mathrm\{d\}|(?<![A-Za-z])d\s*[A-Za-z]\b"
    r"|\\(?:sum|int)(?![A-Za-z])|_\{[^{}]*\}|\^\{[^{}]*\}|[_^][A-Za-z0-9]")
# Commands that name a function of the variable, so they are another factor.
FACTOR_COMMAND_RE = re.compile(r"\\(?:log|ln|exp|sqrt|sin|cos)\b")
OTHER_COMMAND_RE = re.compile(r"\\[A-Za-z]+")


class Finding(NamedTuple):
    path: str
    line: int
    message: str


def operator_title(lines: List[str], div) -> bool:
    """True when the div is titled for the expectation operator itself."""
    opener = TITLE_ATTR_RE.search(lines[div.start])
    if opener and OPERATOR_TITLE_RE.search(opener.group(1) or opener.group(2) or ""):
        return True
    for raw in div.body:
        if not raw.strip():
            continue
        return raw.lstrip().startswith("#") and bool(OPERATOR_TITLE_RE.search(raw))
    return False


def weighted_sum(math: str) -> bool:
    """True for a sum or integral of a mass or density times another factor."""
    if SAMPLE_AVERAGE_RE.search(math):
        return False
    for tail in (math[m.end():] for m in SUM_RE.finditer(math)):
        if not PMF_RE.search(tail):
            continue
        rest = FILLER_RE.sub(" ", PMF_RE.sub(" ", tail))
        rest = FACTOR_COMMAND_RE.sub("F", rest)
        rest = OTHER_COMMAND_RE.sub(" ", rest)
        if LEFTOVER_RE.search(rest):
            return True
    return False


def reasons(lines: List[str], div) -> List[str]:
    if any(ALLOW_RE.search(line) for line in div.body):
        return []
    if operator_title(lines, div):
        return []
    text = base.strip_fences(div.body)
    shown = base.displays(text)
    if any(EXPECTATION_RE.search(d) for d in shown):
        return []
    if any(weighted_sum(d) for d in shown):
        return ["a display writes a probability-weighted sum or integral with no expectation operator"]
    return []


def check_file(path: str, lines: List[str],
               touched: Optional[Set[int]]) -> List[Finding]:
    findings: List[Finding] = []
    for d in base.find_divs(lines):
        if touched is not None and not any(n + 1 in touched
                                           for n in range(d.start, d.end + 1)):
            continue
        why = reasons(lines, d)
        if why:
            findings.append(Finding(path, d.start + 1,
                f"#{d.ident}: {'; '.join(why)} (heuristic). Define a quantity "
                f"as an expectation where one fits. Fix: {ADVICE}"))
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
    base_ref = os.environ.get("DX_BASE_REF", "").strip()
    globs = os.environ.get("DX_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = base.compile_ignores(base._split_list(os.environ.get("DX_PATHS_IGNORE", "")))
    fail = base._env_flag("DX_FAIL", _DEFAULT_FAIL)
    whole_tree = base._env_flag("DX_WHOLE_TREE", False)
    report = run_check(base_ref, globs, ignores, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(f"{'::warning::' if base_ref else ''}Skipping the definition-expectation "
              f"check for this run ({reason}; not falling back to a whole-tree scan).")
        return 0
    for f in report.findings:
        print(f"::{'error' if fail else 'warning'} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("No touched definition writes a weighted sum or integral where an expectation fits.")
        return 0
    print(f"\n{len(report.findings)} definition(s) that could use an expectation.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
