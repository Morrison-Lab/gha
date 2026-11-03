#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a clickbait heading: a question, or a phrase that starts with an
interrogative word.

The lab's rule (Ezra, 2026-11-03, after lds headings such as "What the
coefficients mean", "Fitting: where the cost comes from" and "How sure are the
coefficients?"): a heading is a plain noun phrase that names its content. It
is not a question, and neither it nor a phrase after a colon begins with who,
whom, whose, what, when, where, why, how or which. Rule text: psw,
``chapters/paper-organization.qmd``, "Subsection headings".

Flagged, in a heading the diff adds:

- **A question.** The heading text ends with ``?``.
- **An interrogative start.** The heading, or any phrase after a colon in it,
  begins with one of the words above.

Also flagged, by the same two rules: the title of a fenced div or callout,
which is a heading written inside the div (the ``####`` line that opens a
definition, example or exercise) or a ``title="..."`` attribute on the div's
opening fence (Ezra, 2026-11-03: "titles like this").

What is not counted: headings inside code fences, HTML comments or YAML front
matter; a line carrying ``<!-- check-heading-titles: allow -->``.

Design notes, in the model of ``check-heading-levels`` (whose heading scanner
this reuses):

- **Diff-scoped by default.** A finding is reported only when the heading line
  was added, so existing headings are not swept (Ezra, 2026-11-03).
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``HTT_WHOLE_TREE=true`` scans the
  whole tree, which measures how many headings the corpus carries.
- **Failing by default** (agents ignore warnings; Ezra, 2026-11-02).

Configuration (environment variables, set by the composite action):
  HTT_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  HTT_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  HTT_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  HTT_FAIL          "false" => warn only; default "true".
  HTT_WHOLE_TREE    "true" => scan every tracked matching file in full.
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
ALLOW_MARKER = "check-heading-titles: allow"

INTERROGATIVES = ("who", "whom", "whose", "what", "when", "where", "why",
                  "how", "which")
START_RE = re.compile(r"^[\"'(\[*_\s]*(" + "|".join(INTERROGATIVES) + r")\b",
                      re.IGNORECASE)
ADVICE = ("name the content with a plain noun phrase (psw, Subsection "
          "headings), or add <!-- check-heading-titles: allow -->")


class Finding(NamedTuple):
    path: str
    line: int
    kind: str
    message: str


def phrases(text: str) -> List[str]:
    """The heading and each phrase after a colon, without attributes."""
    plain = hl.ATTR_RE.sub("", text).strip()
    return [plain] + [p for p in plain.split(":")[1:]]


def heading_findings(text: str) -> List[Tuple[str, str]]:
    """The (kind, message) pairs for one heading's text."""
    plain = hl.ATTR_RE.sub("", text).strip()
    out: List[Tuple[str, str]] = []
    if plain.rstrip("*_\"')] ").endswith("?"):
        out.append(("question", f"Heading '{plain}' is a question. "
                                f"Fix: {ADVICE}"))
    for phrase in phrases(text):
        m = START_RE.match(phrase)
        if m:
            out.append(("interrogative",
                        f"Heading '{plain}' has a phrase starting with "
                        f"'{m.group(1)}'. Fix: {ADVICE}"))
            break
    return out


TITLE_ATTR_RE = re.compile(r"""\btitle\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def div_titles(path: str) -> List[Tuple[int, str]]:
    """(line, text) of each title written inside a fenced div in ``path``.

    A title is a heading line inside a div, or the ``title`` attribute on a
    div's opening fence. Code fences, comments and front matter are skipped.
    """
    lines = hl.read_lines(path)
    if lines is None:
        return []
    out: List[Tuple[int, str]] = []
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    in_yaml = bool(lines) and lines[0].strip() == "---"
    depth = 0
    for idx, original in enumerate(lines):
        if in_yaml:
            if idx > 0 and original.strip() in ("---", "..."):
                in_yaml = False
            continue
        raw = original
        if fence is None:
            raw, in_comment = ods.strip_comments(raw, in_comment)
        m = ods.FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        dm = ods.DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                depth += 1
                tm = TITLE_ATTR_RE.search(dm.group(2))
                if tm:
                    out.append((idx + 1, tm.group(1) or tm.group(2)))
            else:
                depth = max(0, depth - 1)
            continue
        hm = hl.HEADING_RE.match(raw)
        if hm and depth > 0:
            out.append((idx + 1, hm.group(2)))
    return out


def scan_file(path: str, root: str) -> List[Finding]:
    """Findings for the headings and div titles written in ``path`` itself."""
    lines = hl.read_lines(path) or []
    found: List[Finding] = []
    for heading, own in hl.scan_headings(path, root):
        if not own:
            continue
        if ALLOW_MARKER in lines[heading.line - 1]:
            continue
        for kind, message in heading_findings(heading.text):
            found.append(Finding(heading.path, heading.line, kind, message))
    for line, text in div_titles(path):
        if ALLOW_MARKER in lines[line - 1]:
            continue
        for kind, message in heading_findings(text):
            found.append(Finding(path, line, kind, message))
    return found


class Report(NamedTuple):
    findings: List[Finding]
    files: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Report findings whose heading line was added since ``base_ref``."""
    root = os.getcwd()
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
    seen: Set[Tuple[str, int, str]] = set()
    for rel in sorted(files):
        for f in scan_file(rel, root):
            key = (rel, f.line, f.kind)
            if key in seen:
                continue
            if not whole_tree and f.line not in keep.get(rel, set()):
                continue
            seen.add(key)
            kept.append(Finding(rel, f.line, f.kind, f.message))
    return Report(kept, len(files), False)


def main() -> int:
    base_ref = os.environ.get("HTT_BASE_REF", "").strip()
    globs = os.environ.get("HTT_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = ods.compile_ignores(ods._split_list(os.environ.get("HTT_PATHS_IGNORE", "")))
    fail = ods._env_flag("HTT_FAIL", _DEFAULT_FAIL)
    whole_tree = ods._env_flag("HTT_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the heading-title check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every heading the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.files} file(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for f in report.findings:
        print(f"::{severity} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("No heading is a question or starts with an interrogative.")
        return 0
    print(f"\n{len(report.findings)} clickbait heading(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
