#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an exercise paragraph that mixes scenario information with the task.

The lab's rule (Ezra, 2026-11-02; Morrison-Lab/psw teaching chapter): the
instruction or question of an exercise goes in its own paragraph, apart from
the scenario information. A reader scanning for the task then finds it
without rereading the setup.

What is flagged: a paragraph of an exercise div (id ``exr-...``) with a task
sentence and a non-task sentence. A task sentence ends with a question mark,
or starts with an imperative task verb such as Show, Find, Compute, Estimate,
Explain or Derive, unless a verb form follows within two words ("Count data
are skewed." is scenario). The verb forms are a short list of auxiliaries, so
"Test scores improved." still reads as a task; exempt such an exercise with
the comment below. Every other sentence in prose counts as scenario.
An exercise nested inside another exercise is not examined separately, and a
skip div (solution or callout) nested inside a skipped div is part of it. A
paragraph of only tasks, or of only scenario, is fine, and so is a paragraph
of the task followed by nothing.

Not examined: nested solution divs (``#sol-``, ``.sol``, ``.solution``,
``.answer``), callouts (hints), code fences, display math, HTML comments,
lists, tables, headings and shortcodes. Math, inline code and the abbreviations
"e.g." and "i.e." never end a sentence. ``<!-- question-paragraph-ok: reason -->``
inside an exercise exempts it.

Sentences are found by punctuation, not by line, so a sentence broken across
lines at a clause counts once.

Diff-scoped like check-bare-yes-no: a finding is reported only when the diff
adds a line of the paragraph, an untouched exercise keeps its form, and with
no base ref the check skips rather than scanning the whole tree.
``EQP_WHOLE_TREE=true`` measures a corpus. Needs Python 3.9 or later.

Configuration (environment variables, set by the composite action):
  EQP_BASE_REF    Git ref/SHA to diff against. Empty and not whole-tree => skip.
  EQP_GLOBS       Space-separated git pathspecs (default: '*.qmd').
  EQP_FAIL        "true" (default) => exit 1 on a finding; "false" => warnings.
  EQP_WHOLE_TREE  "true" => scan every tracked matching file in full.
"""

import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402
import mdmask  # noqa: E402

DEFAULT_GLOBS = "*.qmd"
ADVICE = ("put the instruction or question in its own paragraph, "
          "after the scenario information")

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
EXR_RE = re.compile(r"#exr-")
SKIP_DIV_RE = re.compile(r"#sol-|\.(?:sol|solution|answer)(?![\w-])|\.callout")
OK_RE = re.compile(r"<!--\s*question-paragraph-ok:")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
BREAK_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\||#{1,6}\s|\{\{<|\$\$|>)")
MATH_RE = re.compile(r"\$[^$]*\$")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
ABBREV_RE = re.compile(r"\b(?:e\.g|i\.e|vs|etc|cf|Fig|No)\.")
SPLIT_RE = re.compile(r"(?<=[.?!])[\"')\]]*\s+")
LEAD_RE = re.compile(r"^(?:then|also|next|finally|and|now|lastly),?\s+", re.I)

TASK_VERBS = frozenset("""
    answer apply argue build calculate check choose classify compare compute
    construct count decide define derive describe determine draw estimate
    evaluate explain express find fit give identify implement interpret
    justify list match name plot predict prove report rewrite round say
    select show simplify sketch solve state test verify write
""".split())


VERB_FORMS = frozenset("""
    is are was were be been has have had does did can could will would may
    might should must differ differs
""".split())


class Finding(NamedTuple):
    line: int
    end: int
    snippet: str


def sentences(paragraph: str) -> List[str]:
    """Sentences of a paragraph, with math, code and links flattened."""
    text = COMMENT_RE.sub(" ", paragraph)
    text = mdmask.PARAGRAPH_CODE_SPAN_RE.sub("C", text)
    text = MATH_RE.sub("M", text)
    text = LINK_RE.sub(r"\1", text)
    text = ABBREV_RE.sub("abbr", text)
    return [s.strip() for s in SPLIT_RE.split(" ".join(text.split())) if s.strip()]


def is_task(sentence: str) -> bool:
    """Whether a sentence asks a question or gives an instruction."""
    if sentence.rstrip("\"')]*_ ").endswith("?"):
        return True
    text = LEAD_RE.sub("", sentence.lstrip("(*_\"' "))
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", text[:60])]
    if not words or words[0] not in TASK_VERBS:
        return False
    # "Count data are skewed." has a verb of its own after the noun phrase.
    return not VERB_FORMS.intersection(words[1:3])


def mixed(paragraph: str) -> bool:
    """Whether a paragraph holds both a task and scenario information."""
    kinds = {is_task(s) for s in sentences(paragraph)}
    return kinds == {True, False}


def paragraphs(body: List[tuple]) -> List[tuple]:
    """Paragraphs as (first line number, text) from (number, line) pairs."""
    out: List[tuple] = []
    cur: List[tuple] = []

    def close() -> None:
        if cur:
            out.append((cur[0][0], cur[-1][0], " ".join(t for _, t in cur)))
            cur.clear()

    in_math = False
    for number, raw in body:
        if raw.strip().startswith("$$"):
            close()
            in_math = not (in_math or raw.strip().endswith("$$") and len(raw.strip()) > 2)
            continue
        if in_math:
            in_math = "$$" not in raw
            continue
        if not raw.strip() or BREAK_RE.match(raw):
            close()
            continue
        cur.append((number, raw.strip()))
    close()
    return out


def exercises(lines: List[str]) -> List[Finding]:
    """Mixed paragraphs of each exercise div, one finding per paragraph."""
    found: List[Finding] = []
    fence: Optional[str] = None
    in_comment = False
    depth = 0
    cur: Optional[Dict] = None
    for idx, raw in enumerate(lines):
        lineno = idx + 1
        if cur is not None and OK_RE.search(raw):
            cur["ok"] = True
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
        dm = DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                attrs = dm.group(2)
                if cur is None and EXR_RE.search(attrs):
                    cur = {"depth": depth, "skip": None, "body": [], "ok": False}
                elif cur is not None and cur["skip"] is None and SKIP_DIV_RE.search(attrs):
                    cur["skip"] = depth
                depth += 1
            elif depth > 0:
                depth -= 1
                if cur is not None and depth == cur["depth"]:
                    if not cur["ok"]:
                        for first, last, text in paragraphs(cur["body"]):
                            if mixed(text):
                                found.append(Finding(first, last, text[:60]))
                    cur = None
                elif cur is not None and cur["skip"] == depth:
                    cur["skip"] = None
            continue
        if cur is not None and cur["skip"] is None:
            cur["body"].append((lineno, raw))
    return found


def added_lines(diff: str) -> Dict[str, Set[int]]:
    """Added line numbers per path from ``git diff -U0`` output."""
    added, _deleted = diffscope.parse_diff(diff)
    return {path: set(lines) for path, lines in added.items()}


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
    return None if diff is None else dict(added_lines(diff))


# check-exercise-ends-with-task loads this script and calls ``_flag``.
_flag = diffscope.env_flag


def touched(item: Finding, keep: Optional[Set[int]]) -> bool:
    """Whether the diff adds a line of the paragraph (None = every line)."""
    if keep is None:
        return True
    return any(item.line <= n <= item.end for n in keep)


def main() -> int:
    base_ref = os.environ.get("EQP_BASE_REF", "").strip()
    globs = os.environ.get("EQP_GLOBS", DEFAULT_GLOBS).split() or [DEFAULT_GLOBS]
    fail = _flag("EQP_FAIL", True)
    whole = _flag("EQP_WHOLE_TREE", False)
    wanted = wanted_lines(base_ref, globs, whole)
    if wanted is None:
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the exercise question paragraph check for this run "
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
        for item in exercises(lines):
            if touched(item, wanted[rel]):
                findings += 1
                print(f"::{severity} file={rel},line={item.line}::Paragraph "
                      f"'{item.snippet}...' mixes scenario information with the "
                      f"task. Fix: {ADVICE}")
    print(f"Examined {len(wanted)} file(s); {findings} paragraph(s) flagged.")
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
