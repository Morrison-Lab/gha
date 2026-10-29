#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a key equation written inline in a proof instead of in display math.

The lab's rule (Ezra, 2026-10-28; Morrison-Lab/psw mathematical-writing
chapter): a key equation is a theorem's conclusion, an equation a proof builds
toward, or one a later step refers to. It goes in a display (``$$ ... $$``),
never inline. The motivating case was the proof of the normal equations,
which wrote ``yields $\tp{D} D \beta = \tp{D} y$.`` in the middle of a line.

Deciding what a reader should remember is not mechanical, so this is a
partial heuristic with two signals, both only inside a proof div (class
``.proof`` or ``proof``, or an id starting ``prf-``):

  restated   An inline equation whose normalized text equals a displayed
             equation (``$$ ... $$``) elsewhere in the same file, which is the
             parent theorem's statement in the lab's one-div-per-file layout.
  concluded  An inline equation (it contains =, <, >, \le, \ge, \neq or
             \approx) that ends its sentence and follows a concluding word
             (yields, gives, implies, so, thus, hence, therefore, forces), or
             whose next line opens with So, Hence, Therefore or Thus.

What it cannot do: it cannot tell a key equation from a routine one, so it
misses a key equation with no cue word and may flag a minor step. Put
``<!-- inline-ok -->`` on the line to accept an inline equation. Inline
code, code fences and HTML comments are skipped, and an equation split over
two lines is not seen.

Diff-scoped like check-bare-yes-no: only an added line is reported, and with no
base ref the check skips. ``KED_WHOLE_TREE=true`` measures a corpus.

Configuration (environment variables, set by the composite action):
  KED_BASE_REF    Git ref/SHA to diff against. Empty and not whole-tree => skip.
  KED_GLOBS       Space-separated git pathspecs (default: '*.qmd').
  KED_FAIL        "false" => warnings only; default "true" => exit 1.
  KED_WHOLE_TREE  "true" => scan every tracked matching file in full.
"""

import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Set, Tuple

DEFAULT_GLOBS = "*.qmd"
OK_MARK = "inline-ok"
ADVICE = ("put the equation in display math ($$ ... $$) and let the sentence "
          "introduce it; add <!-- inline-ok --> to the line to accept it inline")

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
PROOF_RE = re.compile(r"(?:^|[\s{])proof(?![\w-])|\.proof(?![\w-])|#prf-")
INLINE_RE = re.compile(r"(?<![\\$])\$(?!\$)((?:[^$\\]|\\.)+?)\$(?!\$)")
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")
RELATION_RE = re.compile(r"(?<![<>!:\\])=|\\le(?![a-zA-Z])|\\ge(?![a-zA-Z])|\\neq|\\approx|[<>]")
CUE_BEFORE_RE = re.compile(
    r"\b(?:yields?|gives?|giving|implies|so|thus|hence|therefore|forces|obtain(?:ing)?)[ ,:]*$",
    re.IGNORECASE)
CUE_NEXT_RE = re.compile(r"^\s*(?:So|Hence|Therefore|Thus)\b")
SENTENCE_END_RE = re.compile(r"^\s*[.;]?\s*$")
DISPLAY_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
DISPLAY_TAG_RE = re.compile(r"\{#[^}]*\}\s*$")


def normalize(math: str) -> str:
    """Compare equations ignoring spacing, sizing commands, labels and end punctuation."""
    text = DISPLAY_TAG_RE.sub("", math)
    text = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg)(?![a-zA-Z])", "", text)
    text = re.sub(r"\s+", "", text)
    return text.rstrip(".,;")


def _mask_code(line: str) -> str:
    return CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), line)


def display_equations(lines: List[str]) -> Set[str]:
    """Normalized text of every ``$$ ... $$`` display in the file, outside code."""
    kept: List[str] = []
    fence: Optional[str] = None
    for raw in lines:
        fm = FENCE_RE.match(raw)
        if fence is not None:
            if fm and fm.group(1)[0] == fence:
                fence = None
            continue
        if fm:
            fence = fm.group(1)[0]
            continue
        kept.append(raw)
    found = {normalize(m.group(1)) for m in DISPLAY_RE.finditer("\n".join(kept))}
    return {eq for eq in found if len(eq) >= 3}


def inline_key_equations(lines: List[str]) -> List[Tuple[int, str, str]]:
    """``(line number, inline math, reason)`` for each flagged inline equation in a proof."""
    displays = display_equations(lines)
    found: List[Tuple[int, str, str]] = []
    fence: Optional[str] = None
    in_comment = False
    in_display = False
    depth = 0
    proof_depth: Optional[int] = None
    for idx, raw in enumerate(lines):
        if in_comment:
            in_comment = "-->" not in raw
            continue
        if raw.lstrip().startswith("<!--"):
            in_comment = "-->" not in raw
            continue
        fm = FENCE_RE.match(raw)
        if fence is not None:
            if fm and fm.group(1)[0] == fence:
                fence = None
            continue
        if fm:
            fence = fm.group(1)[0]
            continue
        if raw.count("$$") % 2 == 1:
            in_display = not in_display
            continue
        if in_display or raw.strip().startswith("$$"):
            continue
        dm = DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                if proof_depth is None and PROOF_RE.search(dm.group(2)):
                    proof_depth = depth
                depth += 1
            elif depth > 0:
                depth -= 1
                if proof_depth is not None and depth == proof_depth:
                    proof_depth = None
            continue
        if proof_depth is None or OK_MARK in raw:
            continue
        line = _mask_code(raw)
        following = lines[idx + 1] if idx + 1 < len(lines) else ""
        for m in INLINE_RE.finditer(line):
            math = m.group(1).strip()
            if normalize(math) in displays:
                found.append((idx + 1, math, "restates a displayed equation of the theorem"))
                continue
            if not RELATION_RE.search(math):
                continue
            if not SENTENCE_END_RE.match(line[m.end():]):
                continue
            if CUE_BEFORE_RE.search(line[:m.start()]) or CUE_NEXT_RE.match(following):
                found.append((idx + 1, math, "ends a concluding sentence"))
    return found


def added_lines(diff: str) -> Dict[str, Set[int]]:
    """Added line numbers per path from ``git diff -U0`` output."""
    added: Dict[str, Set[int]] = {}
    path: Optional[str] = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = None if target == "/dev/null" else target.removeprefix("b/")
            if path is not None:
                added.setdefault(path, set())
            continue
        m = HUNK_RE.match(line)
        if m and path is not None:
            start = int(m.group(1))
            count = 1 if m.group(2) is None else int(m.group(2))
            added[path].update(range(start, start + count))
    return added


def _git(args: List[str]) -> Optional[str]:
    res = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace")
    return res.stdout if res.returncode == 0 else None


def wanted_lines(base_ref: str, globs: List[str], whole_tree: bool
                 ) -> Optional[Dict[str, Optional[Set[int]]]]:
    """Files to scan, each with its added lines (None = every line)."""
    if whole_tree:
        out = _git(["ls-files", "--", *globs])
        return None if out is None else {p: None for p in out.splitlines() if p}
    if not base_ref:
        return None
    base = _git(["merge-base", base_ref, "HEAD"])
    if not base or not base.strip():
        return None
    diff = _git(["diff", "-U0", "--no-color", "--no-ext-diff", base.strip(),
                 "--", *globs])
    return None if diff is None else dict(added_lines(diff))


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value in ("1", "true", "yes", "on")


def main() -> int:
    base_ref = os.environ.get("KED_BASE_REF", "").strip()
    globs = os.environ.get("KED_GLOBS", DEFAULT_GLOBS).split() or [DEFAULT_GLOBS]
    fail = _flag("KED_FAIL", True)
    whole = _flag("KED_WHOLE_TREE", False)
    wanted = wanted_lines(base_ref, globs, whole)
    if wanted is None:
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the key-equation display check for this run "
              f"({'could not diff against ' + repr(base_ref) if base_ref else 'no base-ref given'}).")
        return 0
    severity = "error" if fail else "warning"
    findings = 0
    for rel in sorted(wanted):
        try:
            with open(rel, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().split("\n")
        except OSError:
            continue
        keep = wanted[rel]
        for number, math, reason in inline_key_equations(lines):
            if keep is None or number in keep:
                findings += 1
                print(f"::{severity} file={rel},line={number}::Inline equation "
                      f"'{math[:40]}' {reason}. Fix: {ADVICE}.")
    print(f"Examined {len(wanted)} file(s); {findings} inline key equation(s) flagged.")
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
