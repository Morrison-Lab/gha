#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an executed code chunk that sets ``#| code-fold: false``.

The lab's rule (Ezra, 2026-11-05; Morrison-Lab/psw teaching chapter, "Set
`code-fold` by whether the prose mentions the code"): every executed chunk is
``show`` (the prose mentions the code, so it starts open and can be folded) or
``true`` (the prose does not, so it starts hidden and can be opened).
``false`` removes the toggle and gains nothing, because ``show`` also keeps the
code and its output together.

What is flagged: a ``#| code-fold: false`` option line (also ``FALSE`` or a
quoted ``"false"``) in the option block at the top of a chunk whose fence
names an engine, such as ``{r}``, ``{python}`` or ``{julia}``. A plain fence
has no options. A ``code-fold: false`` anywhere else, such as in front matter,
is not examined.

With ``CCF_REQUIRE_SUMMARY=true`` (off by default) it also flags a new
executed chunk whose code folds but that sets no ``code-summary``, so the
toggle says what the hidden code does rather than a site-wide "Show code"
(lds#2849). A chunk folds when it sets ``code-fold: true`` or ``show``, or
sets no ``code-fold`` while ``CCF_DEFAULT_FOLD`` is true (the project's own
``code-fold`` default). A chunk with ``echo: false`` or ``include: false``
shows no code and is skipped. A chunk counts as new when the diff adds its
opening fence line.

Diff-scoped like check-bare-yes-no: only an added line is reported, an
untouched chunk keeps its option, and with no base ref the check skips rather
than scanning the whole tree. ``CCF_WHOLE_TREE=true`` measures a corpus.

Configuration (environment variables, set by the composite action):
  CCF_BASE_REF    Git ref/SHA to diff against. Empty and not whole-tree => skip.
  CCF_GLOBS       Space-separated git pathspecs (default: '*.qmd').
  CCF_FAIL        "false" => warnings only; default "true" => exit 1.
  CCF_WHOLE_TREE  "true" => scan every tracked matching file in full.
  CCF_REQUIRE_SUMMARY  "true" => also flag a new folded chunk with no code-summary.
  CCF_DEFAULT_FOLD     "true" => a chunk with no code-fold option folds (default "false").
"""

import os
import re
import sys
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

DEFAULT_GLOBS = "*.qmd"
ADVICE = ("set `#| code-fold: show` when the prose mentions the code, "
          "or `#| code-fold: true` when it does not")

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
ENGINE_RE = re.compile(r"^\s*\{[ \t]*[A-Za-z][\w-]*[ \t,}]")
OPTION_RE = re.compile(r"^[ \t]*#\|(.*)$")
FOLD_FALSE_RE = re.compile(r"^\s*code-fold\s*:\s*[\"']?false[\"']?\s*$", re.IGNORECASE)
OPTION_KV_RE = re.compile(r"^\s*([A-Za-z][\w-]*)\s*:\s*(.*?)\s*$")
SUMMARY_ADVICE = ('add `#| code-summary: "Code: <what the code does>"` so the '
                  'toggle says what the hidden code does')


def fold_false_options(lines: List[str]) -> List[Tuple[int, str]]:
    """``(line number, text)`` of each ``code-fold: false`` option in an executed chunk."""
    found: List[Tuple[int, str]] = []
    fence: Optional[str] = None
    executed = False
    in_options = False
    for idx, raw in enumerate(lines):
        fm = FENCE_RE.match(raw)
        if fence is None:
            if fm:
                fence = fm.group(1)[0]
                executed = bool(ENGINE_RE.match(fm.group(2)))
                in_options = executed
            continue
        if fm and fm.group(1)[0] == fence and not fm.group(2).strip():
            fence = None
            executed = False
            in_options = False
            continue
        if not (executed and in_options):
            continue
        om = OPTION_RE.match(raw)
        if om:
            if FOLD_FALSE_RE.match(om.group(1)):
                found.append((idx + 1, raw.strip()))
        else:
            in_options = False
    return found


def _option_value(value: str) -> str:
    """An option value without quotes, in lower case."""
    return value.strip().strip("\"'").strip().lower()


def chunk_options(lines: List[str]) -> List[Tuple[int, Dict[str, str]]]:
    """``(fence line number, options)`` for each executed chunk.

    The options are the ``#|`` lines at the top of the chunk, keyed by name;
    a later value for the same key wins, as knitr reads it.
    """
    chunks: List[Tuple[int, Dict[str, str]]] = []
    fence: Optional[str] = None
    options: Optional[Dict[str, str]] = None
    for idx, raw in enumerate(lines):
        fm = FENCE_RE.match(raw)
        if fence is None:
            if fm:
                fence = fm.group(1)[0]
                if ENGINE_RE.match(fm.group(2)):
                    options = {}
                    chunks.append((idx + 1, options))
            continue
        if fm and fm.group(1)[0] == fence and not fm.group(2).strip():
            fence = None
            options = None
            continue
        if options is None:
            continue
        om = OPTION_RE.match(raw)
        if not om:
            options = None
            continue
        kv = OPTION_KV_RE.match(om.group(1))
        if kv:
            options[kv.group(1).lower()] = _option_value(kv.group(2))
    return chunks


def missing_summaries(lines: List[str], default_fold: bool) -> List[int]:
    """Fence line numbers of executed chunks that fold but set no code-summary."""
    found: List[int] = []
    for number, options in chunk_options(lines):
        if options.get("echo") == "false" or options.get("include") == "false":
            continue
        fold = options.get("code-fold")
        folds = fold in ("true", "show") if fold is not None else default_fold
        if folds and not options.get("code-summary"):
            found.append(number)
    return found


def added_lines(diff: str) -> Dict[str, Set[int]]:
    """Added line numbers per path from ``git diff -U0`` output."""
    added, _deleted = diffscope.parse_diff(diff)
    return {path: set(numbered) for path, numbered in added.items()}


def wanted_lines(base_ref: str, globs: List[str], whole_tree: bool
                 ) -> Optional[Dict[str, Optional[Set[int]]]]:
    """Files to scan, each with its added lines (None = every line)."""
    if whole_tree:
        paths = diffscope.git_paths(["ls-files", "--", *globs])
        return None if paths is None else {p: None for p in paths}
    if not base_ref:
        return None
    base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
    if not base or not base.strip():
        return None
    diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                              base.strip(), "--", *globs])
    return None if diff is None else added_lines(diff)


_flag = diffscope.env_flag


def main() -> int:
    base_ref = os.environ.get("CCF_BASE_REF", "").strip()
    globs = os.environ.get("CCF_GLOBS", DEFAULT_GLOBS).split() or [DEFAULT_GLOBS]
    fail = _flag("CCF_FAIL", True)
    whole = _flag("CCF_WHOLE_TREE", False)
    require_summary = _flag("CCF_REQUIRE_SUMMARY", False)
    default_fold = _flag("CCF_DEFAULT_FOLD", False)
    wanted = wanted_lines(base_ref, globs, whole)
    if wanted is None:
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the code-fold check for this run "
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
        for number, text in fold_false_options(lines):
            if keep is None or number in keep:
                findings += 1
                print(f"::{severity} file={rel},line={number}::Chunk sets "
                      f"'{text[:40]}'. Fix: {ADVICE}.")
        if not require_summary:
            continue
        for number in missing_summaries(lines, default_fold):
            if keep is None or number in keep:
                findings += 1
                print(f"::{severity} file={rel},line={number}::New chunk folds its "
                      f"code but sets no code-summary. Fix: {SUMMARY_ADVICE}.")
    print(f"Examined {len(wanted)} file(s); {findings} code-fold finding(s) flagged.")
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
