#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a definition of a function of one or two inputs that has no graph.

The lab's rule (Ezra, 2026-11-10; Morrison-Lab/psw#574): "every definition
for a function of one or two inputs should include a graph of that function
(in 2d or 3d, respectively)". psw records it in ``chapters/defining-terms.qmd``.

A definition div (``#def-``) is a candidate when its first display equation
defines a function application with one or two arguments: the left-hand side,
up to the first ``=``, ``:=``, ``\eqdef``, ``\coloneqq``, ``\triangleq`` or
``\equiv``, is exactly ``name(a)``, ``name(a, b)``, ``name\paren{a}`` or
``\namef{a, b}``, and each argument is a lowercase Latin or Greek letter with an
optional subscript or superscript. Uppercase letters name sets, events and
random variables, and a vector or matrix macro (``\vx``, ``\mX``) or an
expression is not a scalar input, so a definition with such an argument is not
a candidate.

This is a heuristic, so the check warns by default. Known limits: only the
first display equation outside HTML comments is read, so a definition that
states its defining equation second is skipped; and any ``=`` counts as
defining, so a first equation that states a property of a named function, such
as ``\log(x) = y``, makes the div a candidate.

What counts as a graph inside the div is what ``check-exm-figures`` counts as
a figure (an image, a ``fig-`` chunk or div, an ``@fig-`` reference or a
``_fig`` subfile include), and this script imports that test. A definition is
exempt when its div holds ``<!-- no-graph: reason -->`` with a non-empty reason.

Diff-scoped like ``check-exm-figures``: a definition is reported only when it
holds a line the diff adds (moved lines and blank lines do not count), the
check skips rather than falling back to a whole-tree scan when the diff cannot
be computed, and ``FNG_WHOLE_TREE=true`` measures the whole corpus.

Configuration (environment variables, set by the composite action):
  FNG_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  FNG_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  FNG_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  FNG_FAIL          "true" => annotations are errors and fail; default "false".
  FNG_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

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


exf = _load_sibling("check-exm-figures")
ods = exf.ods

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = False

ADVICE = (
    "add a graph of the function inside the definition div, after the "
    "defining equation (2D for one input, 3D for two), or add "
    "<!-- no-graph: reason --> inside the div"
)

DEF_RE = re.compile(r"#def-")
EXEMPT_RE = re.compile(r"<!--\s*no-graph:\s*(?!-->)\S")
DEFINES_RE = re.compile(r":=|\\eqdef|\\coloneqq|\\triangleq|\\equiv|\\doteq|=")
_SUB = r"(?:_\{[^{}]*\}|_\\?\w+)?(?:\^\{[^{}]*\}|\^\\?\w+)?"
_NAME = r"(?:\\[A-Za-z]+|[A-Za-z])" + _SUB
_GREEK = (r"alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|vartheta|"
          r"kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|phi|varphi|chi|psi|omega")
# One scalar argument: a Latin or Greek letter, with an optional subscript or
# superscript. A vector or matrix macro, a set, an event or an expression is
# not a scalar input, so a definition whose argument is one is not a candidate.
SCALAR_ARG_RE = re.compile(r"(?:[a-z]|\\(?:" + _GREEK + r"))" + _SUB + r"'*")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
APPLICATION_RES = [re.compile(p) for p in (
    r"^" + _NAME + r"\s*(?:\\left)?\(\s*(?P<args>[^()]*?)\s*(?:\\right)?\)$",
    r"^" + _NAME + r"\s*\\paren\{(?P<args>[^{}]*)\}$",
    r"^\\[A-Za-z]+f\{(?P<args>[^{}]*)\}$",
)]


class Definition(NamedTuple):
    start: int  # 1-based line of the opening fence
    end: int    # 1-based line of the closing fence
    attrs: str
    arity: int


def first_display_math(body: List[str]) -> Optional[str]:
    """Text of the first ``$$ ... $$`` block outside HTML comments, or None."""
    text = COMMENT_RE.sub("", "\n".join(body))
    m = re.search(r"\$\$(.*?)\$\$", text, re.S)
    return m.group(1) if m else None


def split_args(args: str) -> List[str]:
    """An argument list split at its top-level commas."""
    depth = 0
    parts = [""]
    for ch in args:
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("")
        else:
            parts[-1] += ch
    return parts


def defined_arity(math: str) -> Optional[int]:
    """Arity of the function application a display equation defines.

    None when the equation's left-hand side is not an application of one or
    two scalar arguments.
    """
    m = DEFINES_RE.search(math)
    if not m:
        return None
    lhs = math[:m.start()]
    lhs = re.sub(r"\\begin\{\w+\*?\}|&|\\[,;!]|\\quad", " ", lhs).strip()
    for rx in APPLICATION_RES:
        am = rx.search(lhs)
        if not am:
            continue
        parts = [a.strip() for a in split_args(am.group("args"))]
        if not all(SCALAR_ARG_RE.fullmatch(a) for a in parts):
            return None
        return len(parts) if len(parts) in (1, 2) else None
    return None


def scan_definitions(lines: List[str]) -> List[Definition]:
    """Every ``#def-`` div that defines a function of one or two inputs."""
    found: List[Definition] = []
    for div in exf.scan_crossref_divs(lines):
        if not DEF_RE.search(div.attrs):
            continue
        math = first_display_math(lines[div.start:div.end - 1])
        arity = defined_arity(math) if math else None
        if arity:
            found.append(Definition(div.start, div.end, div.attrs, arity))
    return found


def scan_file(lines: List[str], keep: Optional[Set[int]]) -> Tuple[List[Definition], int]:
    """Candidate definitions with no graph that hold a kept line, and candidates seen."""
    missing: List[Definition] = []
    defs = scan_definitions(lines)
    for d in defs:
        body = lines[d.start - 1:d.end]
        if exf.has_figure(body) or any(EXEMPT_RE.search(line) for line in body):
            continue
        if keep is None or any(d.start <= n <= d.end for n in keep):
            missing.append(d)
    return missing, len(defs)


def format_message(d: Definition) -> str:
    ident = re.search(r"#def-[\w:.-]+", d.attrs)
    name = ident.group(0) if ident else "definition"
    inputs = "one input" if d.arity == 1 else "two inputs"
    return f"Definition {name} defines a function of {inputs} and has no graph. Fix: {ADVICE}"


class Report(NamedTuple):
    findings: List[Tuple[str, Definition]]
    files: int
    lines: int
    candidates: int
    skipped: bool


def changed_lines(base_ref: str, globs: List[str], ignores: list,
                  whole_tree: bool) -> Optional[Dict[str, Optional[Set[int]]]]:
    """Files to scan, each with its added lines (None = the whole file)."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = ods._run_git(["ls-files", "--", *globs])
        if out is None:
            return None
        for rel in out.splitlines():
            if rel and not ods._ignored(rel, ignores):
                wanted[rel] = None
        return wanted
    if not base_ref:
        return None
    base = ods._run_git(["merge-base", base_ref, "HEAD"])
    if base is None or not base.strip():
        return None
    diff = ods._run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
    if diff is None:
        return None
    added, deleted = ods.parse_diff(diff)
    for rel, numbered in added.items():
        if not ods._ignored(rel, ignores):
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}
    return wanted


def run_check(base_ref: str, globs: List[str], ignores: list,
              whole_tree: bool) -> Report:
    wanted = changed_lines(base_ref, globs, ignores, whole_tree)
    if wanted is None:
        return Report([], 0, 0, 0, True)
    findings: List[Tuple[str, Definition]] = []
    files = lines = candidates = 0
    for rel in sorted(wanted):
        content = ods._read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        missing, seen = scan_file(content, keep)
        candidates += seen
        findings.extend((rel, d) for d in missing)
    return Report(findings, files, lines, candidates, False)


def main() -> int:
    base_ref = os.environ.get("FNG_BASE_REF", "").strip()
    globs = os.environ.get("FNG_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = ods.compile_ignores(ods._split_list(os.environ.get("FNG_PATHS_IGNORE", "")))
    fail = ods._env_flag("FNG_FAIL", _DEFAULT_FAIL)
    whole_tree = ods._env_flag("FNG_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the function-graph check for this run ({reason}; "
              "not falling back to a whole-tree scan, which would reflag every "
              "definition the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.lines} line(s) across {report.files} file(s), "
          f"{report.candidates} definition(s) of a function of one or two inputs "
          f"(scope: {scope}).")
    severity = "error" if fail else "warning"
    for rel, d in report.findings:
        print(f"::{severity} file={rel},line={d.start}::{format_message(d)}")
    if not report.findings:
        print("Every examined function definition has a graph or a stated exemption.")
        return 0
    print(f"\n{len(report.findings)} function definition(s) have no graph.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
