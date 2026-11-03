#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag self-referential prose: a sentence in which the notes describe
themselves instead of their subject.

The lab's rule (Ezra, 2026-11-03, after lds sentences such as "This exercise
shows that the negative gradient is the best answer, and says what "best"
means here"): write about the content, not the structure of the notes. State
the content directly ("The negative gradient decreases the cost the most"),
and put an overview of a group of items in its own paragraph before the first
item. Rule text: psw, ``chapters/paper-organization.qmd``, "Avoid forward
references".

Flagged, in a line the diff adds: a sentence that starts with "This" or
"These" and a structural noun (exercise, solution, section, chapter, lecture,
page, handout), optionally followed by "and the ones that follow it",
and then a verb that reports what the structure does: shows, establishes,
explains, says, derives, proves, covers, introduces, demonstrates, illustrates,
describes, computes, handles, or "is about".

What is not counted: code fences, HTML comments, YAML front matter; a
sentence that names a figure or table placed beside it ("Table 2 shows the
estimates" and "This figure shows" are fine, so figure, table and example are
not structural nouns here); a line carrying ``<!-- check-self-reference: allow
-->``.

Design notes, in the model of ``check-heading-titles``:

- **Diff-scoped by default.** A finding is reported only when the line was
  added, so existing prose is not swept (Ezra, 2026-11-03).
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``SRF_WHOLE_TREE=true`` scans the
  whole tree, which measures how much of the corpus carries the pattern.
- **Failing by default** (agents ignore warnings; Ezra, 2026-11-02).
- Placement of an overview before its first item is not detectable, so this
  check covers only the self-reference half of the rule.

Configuration (environment variables, set by the composite action):
  SRF_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  SRF_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  SRF_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  SRF_FAIL          "false" => warn only; default "true".
  SRF_WHOLE_TREE    "true" => scan every tracked matching file in full.
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


hl = _load_sibling("check-heading-levels")
ods = hl.ods

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = True
ALLOW_MARKER = "check-self-reference: allow"

NOUNS = ("exercise", "solution", "section", "chapter", "lecture", "page",
         "handout")
VERBS = ("shows?", "establish(?:es)?", "explains?", "says?", "derives?",
         "proves?", "covers?", "introduces?", "demonstrates?", "illustrates?",
         "describes?", "computes?", "handles?", "is about")
# "This exercise shows", "These exercises prove", "This exercise and the ones
# that follow it establish", at the start of a sentence.
PATTERN = re.compile(
    r"(?:^|[.!?]\s+)[\"'(\[*_\s]*(?:This|These|this|these)\s+(?:"
    + "|".join(NOUNS) + r")s?\b(?:\s+and\s+the\s+\w+\s+that\s+follow(?:s)?"
    r"(?:\s+it)?)?\s+(" + "|".join(VERBS) + r")\b(?!\s+(?:up|off|out)\b)",
    re.IGNORECASE)
ADVICE = ("state the content directly, and put an overview of a group of "
          "items in its own paragraph before the first item (psw, Avoid "
          "forward references), or add <!-- check-self-reference: allow -->")


class Finding(NamedTuple):
    path: str
    line: int
    message: str


def prose_lines(lines: List[str]) -> List[Tuple[int, str]]:
    """The (line number, text) pairs outside front matter, code and comments."""
    out: List[Tuple[int, str]] = []
    in_front = bool(lines) and lines[0].strip() == "---"
    in_code = False
    in_comment = False
    for number, raw in enumerate(lines, start=1):
        text = raw.rstrip("\n")
        if number == 1 and in_front:
            continue
        if in_front:
            if text.strip() in ("---", "..."):
                in_front = False
            continue
        if text.lstrip().startswith(("```", "~~~")):
            in_code = not in_code
            continue
        if in_code:
            continue
        stripped = text
        if in_comment:
            if "-->" in stripped:
                in_comment = False
                stripped = stripped.split("-->", 1)[1]
            else:
                continue
        # Cut each complete comment on the line, then an unterminated opener.
        # Lines are split before this point, so no comment spans a newline here.
        while "<!--" in stripped:
            head, _, rest = stripped.partition("<!--")
            if "-->" in rest:
                stripped = head + rest.split("-->", 1)[1]
            else:
                in_comment = True
                stripped = head
                break
        if ALLOW_MARKER in text:
            continue
        out.append((number, stripped))
    return out


def line_findings(text: str) -> Optional[str]:
    """The message for one line of prose, or None."""
    m = PATTERN.search(text)
    if not m:
        return None
    sentence = text[m.start():m.end()].strip(" .!?\"'([*_")
    return (f"'{sentence}...' describes the notes instead of the subject. "
            f"Fix: {ADVICE}")


def scan_file(path: str) -> List[Finding]:
    """Findings for the prose lines of ``path``."""
    lines = hl.read_lines(path) or []
    found: List[Finding] = []
    for number, text in prose_lines(lines):
        message = line_findings(text)
        if message:
            found.append(Finding(path, number, message))
    return found


class Report(NamedTuple):
    findings: List[Finding]
    files: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Report findings whose line was added since ``base_ref``."""
    listing = ods._run_git(["ls-files", "--", *globs])
    if listing is None:
        return Report([], 0, True)
    files = [f for f in listing.splitlines()
             if f and not ods._ignored(f, ignores)]
    keep: Dict[str, Set[int]] = {}
    if not whole_tree:
        if not base_ref:
            return Report([], 0, True)
        base = ods._run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, True)
        diff = ods._run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                             base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, True)
        added, _deleted = ods.parse_diff(diff)
        for rel, numbered in added.items():
            keep[rel] = {n for n, text in numbered.items() if text.strip()}
    kept: List[Finding] = []
    for rel in sorted(files):
        for f in scan_file(rel):
            if not whole_tree and f.line not in keep.get(rel, set()):
                continue
            kept.append(f)
    return Report(kept, len(files), False)


def main() -> int:
    base_ref = os.environ.get("SRF_BASE_REF", "").strip()
    globs = os.environ.get("SRF_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = ods.compile_ignores(ods._split_list(os.environ.get("SRF_PATHS_IGNORE", "")))
    fail = ods._env_flag("SRF_FAIL", _DEFAULT_FAIL)
    whole_tree = ods._env_flag("SRF_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the self-reference check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every sentence the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.files} file(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for f in report.findings:
        print(f"::{severity} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("No added sentence describes the notes instead of the subject.")
        return 0
    print(f"\n{len(report.findings)} self-referential sentence(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
