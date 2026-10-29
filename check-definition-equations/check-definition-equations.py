#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a definition div that shows more than its defining equation.

The lab's rule (Ezra, 2026-10-29; psw ``chapters/defining-terms.qmd``): a
definition div holds only the equation that links the symbol of the defined term
to its definitional expression. An equality between expressions, or an
equivalence between concepts, is stated as a result (``#thm-``, ``#lem-``,
``#cor-`` or ``#prp-``) after the definition.

The check reads every ``#def-`` div and flags it when

- a display equation chains equalities: it has a defining operator (``:=``,
  ``\eqdef``, ``\coloneqq``, ``\triangleq``) followed by another top-level ``=``,
  or, with no defining operator, two or more top-level ``=``;
- the div displays more than one equation; or
- the prose says the defined concept is equivalent to something else
  ("equivalently", "in other words", "is equivalent to", "is the same as",
  "also written", "which equals").

It cannot tell which side of a single ``a = b`` is the defined symbol, so a
definition that displays one equation between two expressions is not flagged.
A display with cases (``\begin{cases}``), or several defining equations that each
carry their own defining operator, is not flagged for its number of equations.
The check is a heuristic: it is warn-only by default, and
``<!-- def-equiv-ok: reason -->`` in the div exempts it.

A div is checked when the diff adds a line inside it, or always with
``DE_WHOLE_TREE=true``. No base-ref means the run is skipped.

Configuration (environment variables, set by the composite action):
  DE_BASE_REF      Git ref/SHA to diff against; empty and not whole-tree => skip.
  DE_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  DE_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  DE_FAIL          "true" => blocking; default "false" (warning annotations).
  DE_WHOLE_TREE    "true" => check every definition div in the tree.
"""

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

_ENGINE_PATH = Path(__file__).resolve().parent.parent / "check-write-idiom" / "check-write-idiom.py"
_spec = importlib.util.spec_from_file_location("check_write_idiom_engine", _ENGINE_PATH)
assert _spec is not None and _spec.loader is not None
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = False

ADVICE = (
    "keep only the equation linking the defined symbol to its definitional "
    "expression in the definition, state the equality or equivalence as a "
    "#thm-, #lem-, #cor- or #prp- div after it, or add "
    "<!-- def-equiv-ok: reason --> to the definition"
)

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
ID_RE = re.compile(r"#(def-[A-Za-z0-9_-]+)")
ALLOW_RE = re.compile(r"<!--\s*def-equiv-ok\b", re.IGNORECASE)
COMMENT_RE = re.compile(r"<!--.*?--!?>", re.DOTALL)
DISPLAY_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
ALIGN_RE = re.compile(r"\\begin\{(align\*?|aligned|eqnarray\*?)\}(.+?)\\end\{\1\}",
                      re.DOTALL)
BA_RE = re.compile(r"\\ba\b(.+?)\\ea\b", re.DOTALL)
CASES_RE = re.compile(r"\\begin\{cases\}.*?\\end\{cases\}", re.DOTALL)
TEXT_RE = re.compile(r"\\(?:text|textrm|mathrm|operatorname)\{[^{}]*\}")
LABEL_RE = re.compile(r"\{#eq-[^}]*\}")
DEFINER_RE = re.compile(r":=|\\eqdef\b|\\coloneqq\b|\\triangleq\b|\\doteq\b")
EQUIV_RE = re.compile(
    r"\b(?:equivalently|in\s+other\s+words|is\s+equivalent\s+to|is\s+the\s+same\s+as|"
    r"also\s+written|which\s+(?:equals|is\s+equal\s+to))\b", re.IGNORECASE)
OPEN, CLOSE = "([{", ")]}"


class Div(NamedTuple):
    ident: str
    start: int  # index into the file's lines
    end: int
    body: Tuple[str, ...]


class Finding(NamedTuple):
    path: str
    line: int
    message: str


def find_divs(lines: List[str]) -> List[Div]:
    """Outermost divs with a ``def-`` id, outside code fences."""
    fence: Optional[Tuple[str, int]] = None
    depth = 0
    cur: Optional[Tuple[int, str, int]] = None
    found: List[Div] = []
    for idx, raw in enumerate(lines):
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
        if not dm:
            continue
        if dm.group(2):
            im = ID_RE.search(dm.group(2))
            if cur is None and im:
                cur = (idx, im.group(1), depth)
            depth += 1
        elif depth > 0:
            depth -= 1
            if cur is not None and depth == cur[2]:
                found.append(Div(cur[1], cur[0], idx, tuple(lines[cur[0] + 1:idx])))
                cur = None
    return found


def strip_fences(body: Tuple[str, ...]) -> str:
    out: List[str] = []
    fence = False
    for raw in body:
        if FENCE_RE.match(raw):
            fence = not fence
            continue
        if not fence:
            out.append(raw)
    return COMMENT_RE.sub("", "\n".join(out))


def displays(text: str) -> List[str]:
    """The math of each display equation: ``$$...$$``, ``align`` and ``\\ba...\\ea``."""
    found = [m.group(1) for m in DISPLAY_RE.finditer(text)]
    rest = DISPLAY_RE.sub(" ", text)
    found += [m.group(2) for m in ALIGN_RE.finditer(rest)]
    found += [m.group(1) for m in BA_RE.finditer(rest)]
    return [LABEL_RE.sub("", d) for d in found]


def top_level_equals(math: str) -> List[int]:
    """Indices of ``=`` signs outside brackets, ``\\text`` and cases."""
    math = CASES_RE.sub(" ", math)
    math = TEXT_RE.sub(lambda m: " " * len(m.group(0)), math)
    depth = 0
    hits: List[int] = []
    for i, c in enumerate(math):
        if i and math[i - 1] == "\\":
            # an escaped brace is a literal set or indicator brace: it still groups
            if c == "{":
                depth += 1
            elif c == "}":
                depth = max(0, depth - 1)
            continue
        if c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth = max(0, depth - 1)
        elif c == "=" and depth == 0:
            prev = math[i - 1] if i else ""
            # ``<=``, ``>=``, ``!=`` and ``==`` are not equalities, and ``:=`` is a
            # definer handled by the caller.
            if prev in "<>!:" or math[i + 1:i + 2] == "=":
                continue
            hits.append(i)
    return hits


def chained(math: str) -> bool:
    """True when the display chains equalities after, or without, a definer."""
    scrubbed = CASES_RE.sub(" ", math)
    definer = DEFINER_RE.search(scrubbed)
    if definer:
        after = scrubbed[definer.end():]
        return bool(top_level_equals(after))
    return len(top_level_equals(scrubbed)) >= 2


def reasons(div: Div) -> List[str]:
    if any(ALLOW_RE.search(line) for line in div.body):
        return []
    text = strip_fences(div.body)
    shown = displays(text)
    out: List[str] = []
    if any(chained(d) for d in shown):
        out.append("a display equation chains equalities after the defining one")
    carries_definer = [d for d in shown if DEFINER_RE.search(CASES_RE.sub(" ", d))]
    if len(shown) > 1 and len(carries_definer) < len(shown):
        out.append(f"the definition displays {len(shown)} equations")
    prose_only = ALIGN_RE.sub(" ", BA_RE.sub(" ", DISPLAY_RE.sub(" ", text)))
    if EQUIV_RE.search(prose_only):
        out.append("the prose states an equivalence")
    return out


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
                f"#{d.ident}: {'; '.join(why)} (heuristic). A definition holds only "
                f"the equation linking the defined symbol to its definitional "
                f"expression; equalities and equivalences are results. Fix: {ADVICE}"))
    return findings


# -- Git plumbing ------------------------------------------------------------

def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


def parse_diff(diff: str) -> Dict[str, Set[int]]:
    """Added, non-blank line numbers per path (the shared engine's parser)."""
    added, _deleted = engine.parse_diff(diff)
    return {path: {n for n, text in numbered.items() if text.strip()}
            for path, numbered in added.items()}


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


def _split_list(value: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,\n]", value) if p.strip()]


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value in ("1", "true", "yes", "on")


def _read_lines(path: str) -> Optional[List[str]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return None
    if lines and lines[-1] == "":
        lines.pop()
    return lines


class Report(NamedTuple):
    findings: List[Finding]
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    out = _run_git(["ls-files", "--", *globs])
    if out is None:
        return Report([], True)
    names = [r for r in out.splitlines()
             if r and not any(g.match(r) for g in ignores)]
    touched: Optional[Dict[str, Set[int]]] = None
    if not whole_tree:
        if not base_ref:
            return Report([], True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], True)
        diff = _run_git([*engine.GIT_DIFF_ARGS, base.strip(), "--", *globs])
        if diff is None:
            return Report([], True)
        touched = parse_diff(diff)
    findings: List[Finding] = []
    for rel in names:
        if touched is not None and not touched.get(rel):
            continue
        content = _read_lines(rel)
        if content is not None:
            findings.extend(check_file(rel, content,
                                       None if touched is None else touched[rel]))
    return Report(sorted(findings), False)


def main() -> int:
    base_ref = os.environ.get("DE_BASE_REF", "").strip()
    globs = os.environ.get("DE_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("DE_PATHS_IGNORE", "")))
    fail = _env_flag("DE_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("DE_WHOLE_TREE", False)
    report = run_check(base_ref, globs, ignores, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(f"{'::warning::' if base_ref else ''}Skipping the definition-equations "
              f"check for this run ({reason}; not falling back to a whole-tree scan).")
        return 0
    for f in report.findings:
        print(f"::{'error' if fail else 'warning'} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("Every touched definition holds only its defining equation.")
        return 0
    print(f"\n{len(report.findings)} definition(s) with more than the defining equation.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
