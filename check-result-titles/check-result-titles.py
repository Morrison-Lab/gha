#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a result div whose title is not a declarative sentence.

The lab's rule (Ezra, 2026-11-20): the title of a result div (a theorem,
lemma, proposition, corollary, or conjecture) is a declarative sentence that
states the result.
A result with a customary name may put the name first, followed by a colon,
as in "Bias-variance decomposition: the expected test error is the variance
plus the squared bias plus the noise".
A noun phrase such as "Derivative of the logistic function" names the topic
of a result without saying what it is.
Rule text: psw, ``chapters/mathematical-writing.qmd``,
"Title a result with the sentence it states".

A title counts as a sentence when it holds a finite verb outside any
relative or subordinate clause, or when its math holds a relation
(``=``, ``<``, ``\le``, ``\in`` and the like).
The verb test is a word list, not a parser:
a finite verb is an auxiliary or copula (``is``, ``has``, ``can``, ...)
or a form of a verb from ``VERB_STEMS``.
Words that are nouns more often than verbs in a title
(``estimate``, ``bounds``, ``squares``, ``weights``, ...) are left out,
because a noun phrase such as "Bounds on the leverage" would otherwise pass.
The first word of a title never counts as its verb,
and the words after ``that``, ``which``, ``when``, ``if`` and the like are
dropped first, so "Number of models that best subset selection fits"
is still flagged.
So a sentence whose only verb is missing from the list is flagged:
add the verb to ``VERB_STEMS``, or mark the line with
``<!-- check-result-titles: allow: <reason> -->``.

The title is the ``title="..."`` attribute on the div's opening fence,
or else the first heading written directly inside the div.
Code fences, HTML comments and YAML front matter are not read.

Design notes, in the model of ``check-heading-titles``:

- **Diff-scoped by default.** A finding is reported only when the title line
  was added, so existing titles are not swept.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``CRT_WHOLE_TREE=true`` scans the
  whole tree, which measures how many titles a corpus carries.
- **Failing by default** (agents ignore warnings; Ezra, 2026-11-02).
  Measured 2026-11-20 over Morrison-Lab/lds (144 result divs, whole tree):
  the check flagged 67 titles, and each one read by hand was a noun phrase,
  a gerund phrase, or a bare name.

Configuration (environment variables, set by the composite action):
  CRT_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  CRT_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  CRT_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  CRT_PREFIXES      Space-separated div id prefixes of result divs
                    (default: 'thm lem prp cor conj').
  CRT_FAIL          "false" => warn only; default "true".
  CRT_WHOLE_TREE    "true" => scan every tracked matching file in full.
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
DEFAULT_PREFIXES = "thm lem prp cor conj"
_DEFAULT_FAIL = True
ALLOW_MARKER = "check-result-titles: allow"

AUXILIARIES = frozenset("""
is are was were be been has have had does do did
can cannot could must may might will would shall should
""".split())

# Base forms of verbs that state results. Each also matches its third-person
# singular form, built by ``_third_person``.
VERB_STEMS = """
absorb achieve add agree apply approach approximate attain become belong
beat cancel carry cause choose classify coincide commute compute contain
converge correspond create decompose decrease define depend determine differ
diverge dominate encourage equal exceed exist explain extend fail favor
flip follow generalize generate give grow hold hurt imply improve include
increase inherit interpolate invert keep lie lose make minimize maximize
move multiply negate outperform overfit penalize predict preserve produce
raise recover reduce regularize remain reproduce require rescale rotate
satisfy separate shrink simplify solve stay succeed take tend transform
underfit vanish
""".split()

# Third-person forms of words that are usually nouns in a title, but verbs
# often enough in a result to keep. Their base forms stay out.
EXTRA_VERBS = frozenset("""
matches yields doubles shifts drops needs helps breaks passes crosses
""".split())


def _third_person(stem: str) -> str:
    if stem.endswith("y") and stem[-2:-1] not in ("a", "e", "i", "o", "u"):
        return stem[:-1] + "ies"
    if re.search(r"(s|x|z|ch|sh|o)$", stem):
        return stem + "es"
    return stem + "s"


VERBS = frozenset(VERB_STEMS) | frozenset(_third_person(s) for s in VERB_STEMS) | EXTRA_VERBS

# Words that open a relative or subordinate clause. A verb after one belongs
# to that clause, not to the title's main clause.
CLAUSE_OPENERS = frozenset("""
that which who whom whose where when whenever if unless because since
while although
""".split())

MATH_RELATION_RE = re.compile(
    r"(?<!\\)[=<>]|\\(?:le|ge|leq|geq|lt|gt|neq|ne|in|notin|ni|subset|subseteq|"
    r"supset|supseteq|approx|sim|simeq|cong|equiv|propto|eqdef|perp|ind|"
    r"implies|iff|Rightarrow|Leftrightarrow|Longrightarrow|to|mapsto)(?![A-Za-z])"
)
MATH_RE = re.compile(r"(?<!\\)\$([^$]+)(?<!\\)\$")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
CODE_RE = re.compile(r"`[^`]*`")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*")
TITLE_ATTR_RE = re.compile(r"""(?<![\w-])title\s*=\s*(?:"([^"]*)"|'([^']*)')""")

ADVICE = ("state the result as a declarative sentence, after its customary "
          "name and a colon if it has one (psw, Title a result with the "
          "sentence it states), or add "
          "<!-- check-result-titles: allow: <reason> -->")


class Finding(NamedTuple):
    path: str
    line: int
    kind: str
    message: str


def is_sentence(title: str) -> bool:
    """Whether ``title`` reads as a declarative sentence."""
    text = hl.ATTR_RE.sub("", title).strip()
    text = LINK_RE.sub(r"\1", text)
    text = CODE_RE.sub(" X ", text)
    for math in MATH_RE.findall(text):
        if MATH_RELATION_RE.search(math):
            return True
    text = MATH_RE.sub(" X ", text)
    words = [w.lower() for w in WORD_RE.findall(text)]
    for i, word in enumerate(words):
        if i > 0 and word in CLAUSE_OPENERS:
            words = words[:i]
            break
    return any(w in AUXILIARIES or w in VERBS or w.endswith("n't")
               for w in words[1:])


def _result_id(attrs: str, prefixes: List[str]) -> Optional[str]:
    """The result div id named in a fence's attributes, if any."""
    for m in re.finditer(r"#([A-Za-z][\w-]*)", attrs):
        ident = m.group(1)
        if ident.split("-", 1)[0] in prefixes and "-" in ident:
            return ident
    return None


def result_titles(path: str, prefixes: List[str]) -> List[Tuple[int, str, str]]:
    """(line, div id, title) of each result div's title in ``path``."""
    lines = hl.read_lines(path)
    if lines is None:
        return []
    out: List[Tuple[int, str, str]] = []
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    in_yaml = bool(lines) and lines[0].strip() == "---"
    # One entry per open div: the result id awaiting its title, or None.
    stack: List[Optional[str]] = []
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
            if stack:
                stack[-1] = None
            continue
        dm = ods.DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                if stack:
                    stack[-1] = None
                ident = _result_id(dm.group(2), prefixes)
                tm = TITLE_ATTR_RE.search(dm.group(2))
                if ident and tm:
                    out.append((idx + 1, ident, tm.group(1) or tm.group(2)))
                    ident = None
                stack.append(ident)
            elif stack:
                stack.pop()
            continue
        if not raw.strip() or not stack or stack[-1] is None:
            continue
        hm = hl.HEADING_RE.match(raw)
        if hm:
            out.append((idx + 1, stack[-1], hm.group(2)))
        stack[-1] = None
    return out


def scan_file(path: str, prefixes: List[str]) -> List[Finding]:
    """Findings for the result-div titles written in ``path``."""
    lines = hl.read_lines(path) or []
    found: List[Finding] = []
    for line, ident, title in result_titles(path, prefixes):
        if ALLOW_MARKER in lines[line - 1]:
            continue
        if is_sentence(title):
            continue
        plain = hl.ATTR_RE.sub("", title).strip()
        found.append(Finding(path, line, "not-a-sentence",
                             f"Title '{plain}' of #{ident} is not a "
                             f"declarative sentence. Fix: {ADVICE}"))
    return found


class Report(NamedTuple):
    findings: List[Finding]
    files: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool, prefixes: Optional[List[str]] = None) -> Report:
    """Report findings whose title line was added since ``base_ref``."""
    prefixes = prefixes or DEFAULT_PREFIXES.split()
    listing = ods._git_paths(["ls-files", "--", *globs])
    if listing is None:
        return Report([], 0, True)
    files = [f for f in listing if f and not ods._ignored(f, ignores)]
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
        added, deleted = ods.parse_diff(diff)
        for rel, numbered in added.items():
            keep[rel] = {n for n, text in numbered.items()
                         if text.strip() and text not in deleted}
    kept: List[Finding] = []
    for rel in sorted(files):
        for f in scan_file(rel, prefixes):
            if not whole_tree and f.line not in keep.get(rel, set()):
                continue
            kept.append(f)
    return Report(kept, len(files), False)


def main() -> int:
    base_ref = os.environ.get("CRT_BASE_REF", "").strip()
    globs = os.environ.get("CRT_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    prefixes = (os.environ.get("CRT_PREFIXES", DEFAULT_PREFIXES).split()
                or DEFAULT_PREFIXES.split())
    ignores = ods.compile_ignores(ods._split_list(os.environ.get("CRT_PATHS_IGNORE", "")))
    fail = ods._env_flag("CRT_FAIL", _DEFAULT_FAIL)
    whole_tree = ods._env_flag("CRT_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree, prefixes)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the result-title check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every title the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.files} file(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for f in report.findings:
        print(f"::{severity} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("Every result-div title is a declarative sentence.")
        return 0
    print(f"\n{len(report.findings)} result title(s) not a declarative sentence.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
