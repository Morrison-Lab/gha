#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a general fact that a proof or solution states instead of citing a lemma.

The lab's rule (Ezra, 2026-10-29; psw ``chapters/teaching.qmd``): extract a lemma
wherever feasible. A general fact that does not depend on its setting (for example
``E[Z^2] = Var(Z) + (E Z)^2`` for any random variable ``Z``) goes in its own
``#lem-`` div on the site that owns the topic, and the proof or solution
that uses it links to the lemma.

The check reads the body of

- each ``#sol-`` div, and
- the proof of each ``#thm-``, ``#lem-``, ``#cor-`` or ``#prp-`` div (a ``.proof``
  div nested in it or directly after it),

and flags a body whose prose states a fact for ``any``, ``every`` or ``all`` of
a kind of mathematical object (a real number, a random variable, a matrix, a function,
and the rest of ``OBJECTS``), in a sentence that also holds math and no inline code,
when the body cites no result
(``@thm-``, ``@lem-``, ``@cor-``, ``@prp-``, or a link to a ``#thm-``, ``#lem-``,
``#cor-`` or ``#prp-`` anchor). A theorem's own statement is not read, since a
theorem is meant to be general.

The check follows ``{{< include ... >}}`` lines, so a page is read in the order a
reader sees it. It is a heuristic that blocks by default (gha#1480), and
``<!-- lemma-ok: reason -->`` in the body exempts it.

A body is checked when the diff adds a line inside it, or always with
``EL_WHOLE_TREE=true``. No base-ref means the run is skipped.

Configuration (environment variables, set by the composite action):
  EL_BASE_REF      Git ref/SHA to diff against; empty and not whole-tree => skip.
  EL_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  EL_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  EL_FAIL          "true" (default) => blocking; "false" => warning annotations.
  EL_WHOLE_TREE    "true" => check every body in the tree.
"""

import os
import posixpath
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402
import mdmask  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = True
RESULT_KINDS = ("thm", "lem", "cor", "prp")

ADVICE = (
    "extract the fact into its own #lem- div (on the prerequisite site that owns "
    "the topic) and link to it, or add <!-- lemma-ok: reason --> to the body"
)

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
ID_RE = re.compile(r"#((?:sol|exm|thm|lem|cor|prp)-[A-Za-z0-9_-]+)")
INCLUDE_RE = re.compile(r"\{\{<\s*include\s+(\S+?)\s*>\}\}")
ALLOW_RE = re.compile(r"<!--\s*lemma-ok\b", re.IGNORECASE)
OBJECTS = (
    "random variable", "random vector", "real number", "natural number", "integer",
    "scalar", "vector", "matrix", "matrices", "function", "set", "subset", "distribution",
    "event", "sequence", "probability", "measure", "random sample", "estimator",
    "model", "loss", "norm",
)
GENERAL_RE = re.compile(
    r"\bfor\s+(?:any|every|all)\s+(?:[A-Za-z-]+\s+){0,2}?(?:"
    + "|".join(OBJECTS) + r")(?:s|es)?\b",
    re.IGNORECASE,
)
NEGATION_RE = re.compile(r"(?:not|no|never|cannot|\w+n['’]t)", re.IGNORECASE)
NEGATION_WINDOW = 4
INLINE_MATH_TOKEN_RE = re.compile(r"\$[^$]*\$")
EDGE_PUNCT_RE = re.compile(r"^[\W_]+|[\W_]+$")
CITES_RESULT_RE = re.compile(r"(?:@|#)(?:thm|lem|cor|prp)-")
PROOF_OPEN_RE = re.compile(r"^ {0,3}:{3,}\s*\{[^}]*\.proof\b")
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


class Div(NamedTuple):
    ident: str
    start: int  # index into the flattened stream
    end: int
    body: Tuple[str, ...]


Stream = List[Tuple[str, int, str]]  # (path, 1-based line, text)


def flatten(path: str, files: Dict[str, List[str]], seen: Tuple[str, ...] = ()) -> Stream:
    """The lines of ``path`` with each include expanded in place."""
    out: Stream = []
    fence: Optional[Tuple[str, int]] = None
    for n, raw in enumerate(files.get(path, []), 1):
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            out.append((path, n, raw))
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            out.append((path, n, raw))
            continue
        inc = INCLUDE_RE.search(raw) if not raw.lstrip().startswith("<!--") else None
        if inc:
            target = posixpath.normpath(posixpath.join(posixpath.dirname(path), inc.group(1)))
            if target in files and target not in seen:
                out.extend(flatten(target, files, seen + (path,)))
                continue
        out.append((path, n, raw))
    return out


def find_divs(stream: Stream) -> List[Div]:
    """Outermost divs with a sol/exm/thm/lem/cor/prp id, outside code fences."""
    fence: Optional[Tuple[str, int]] = None
    depth = 0
    cur: Optional[Tuple[int, str, int]] = None
    found: List[Div] = []
    for idx, (_, _, raw) in enumerate(stream):
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
                found.append(Div(cur[1], cur[0], idx,
                                 tuple(t for _, _, t in stream[cur[0] + 1:idx])))
                cur = None
    return found


def prose(body: Tuple[str, ...]) -> str:
    """The body without comments, code fences and display math."""
    out: List[str] = []
    fence = False
    display = False
    for raw in body:
        raw = mdmask.replace_comments(raw, bang=True)
        if FENCE_RE.match(raw):
            fence = not fence
            continue
        if fence:
            continue
        if raw.strip() == "$$":
            display = not display
            continue
        if not display:
            out.append(raw)
    return " ".join(out)


def _negated(sentence: str, start: int) -> bool:
    """Whether a negation sits in the few words before a quantifier.

    "not a floor for any particular function" denies a universal claim rather
    than making one, so it states no fact a lemma could hold (gha#1480).
    """
    # Inline math counts as one word, however it is spaced, and a word keeps
    # no surrounding punctuation, quotes or emphasis ("**not**").
    head = INLINE_MATH_TOKEN_RE.sub(" MATH ", sentence[:start])
    before = head.split()[-NEGATION_WINDOW:]
    return any(NEGATION_RE.fullmatch(EDGE_PUNCT_RE.sub("", word))
               for word in before)


def states_general_fact(text: str) -> bool:
    """A sentence with 'for any/every/all' that also holds inline math."""
    for sentence in SENTENCE_END_RE.split(mdmask.PARAGRAPH_CODE_SPAN_RE.sub(" ", text)):
        if "$" not in sentence:
            continue
        if any(not _negated(sentence, m.start()) for m in GENERAL_RE.finditer(sentence)):
            return True
    return False


class Finding(NamedTuple):
    path: str
    line: int
    message: str


def _div_end(stream: Stream, start: int, limit: int) -> Optional[int]:
    """Index of the line closing the div that opens at ``start``."""
    depth = 0
    for idx in range(start, limit):
        dm = DIV_RE.match(stream[idx][2])
        if not dm:
            continue
        depth += 1 if dm.group(2) else -1
        if depth == 0:
            return idx
    return None


def proof_span(stream: Stream, thm: Div) -> Optional[Tuple[int, int]]:
    """Stream span of the theorem's proof: nested in it, or directly after it."""
    for idx in range(thm.start + 1, thm.end):
        if PROOF_OPEN_RE.match(stream[idx][2]):
            end = _div_end(stream, idx, thm.end)
            return (idx, end) if end is not None else None
    nxt = thm.end + 1
    while nxt < len(stream) and not stream[nxt][2].strip():
        nxt += 1
    if nxt < len(stream) and PROOF_OPEN_RE.match(stream[nxt][2]):
        end = _div_end(stream, nxt, len(stream))
        return (nxt, end) if end is not None else None
    return None


def check_page(stream: Stream, touched: Optional[Dict[str, Set[int]]]) -> List[Finding]:
    """Findings for the solution and proof bodies of one flattened page."""
    findings: List[Finding] = []
    bodies: List[Tuple[str, int, int]] = []  # (ident, first stream index, last)
    for d in find_divs(stream):
        kind = d.ident.split("-", 1)[0]
        if kind == "sol":
            bodies.append((d.ident, d.start, d.end))
        elif kind in RESULT_KINDS:
            span = proof_span(stream, d)
            if span is not None:
                bodies.append((d.ident, span[0], span[1]))
    for ident, first, last in bodies:
        lines = stream[first:last + 1]
        body = tuple(t for _, _, t in lines)
        if any(ALLOW_RE.search(t) for t in body):
            continue
        if touched is not None and not any(ln in touched.get(p, ()) for p, ln, _ in lines):
            continue
        text = prose(body)
        if CITES_RESULT_RE.search("\n".join(body)) or not states_general_fact(text):
            continue
        path, line, _ = stream[first]
        findings.append(Finding(path, line,
            f"#{ident} states a general fact ('for any/every/all ...') with no lemma "
            f"cited (heuristic). Fix: {ADVICE}"))
    return findings


# -- Git plumbing ------------------------------------------------------------

def added_nonblank(diff: str) -> Dict[str, Set[int]]:
    """Added, non-blank line numbers per path."""
    added, _deleted = diffscope.parse_diff(diff)
    return {path: {n for n, text in lines.items() if text.strip()}
            for path, lines in added.items()}


class Report(NamedTuple):
    findings: List[Finding]
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    paths = diffscope.git_paths(["ls-files", "--", *globs])
    if paths is None:
        return Report([], True)
    names = [r for r in paths if not diffscope.ignored(r, ignores)]
    touched: Optional[Dict[str, Set[int]]] = None
    if not whole_tree:
        if not base_ref:
            return Report([], True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], True)
        diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                                  base.strip(), "--", *globs])
        if diff is None:
            return Report([], True)
        touched = added_nonblank(diff)
    files: Dict[str, List[str]] = {}
    for rel in names:
        content = diffscope.read_lines(rel)
        if content is not None:
            files[rel] = content
    included: Set[str] = set()
    for rel, lines in files.items():
        for raw in lines:
            for inc in INCLUDE_RE.findall(raw):
                included.add(posixpath.normpath(posixpath.join(posixpath.dirname(rel), inc)))
    findings: Set[Finding] = set()
    for rel in files:
        if rel not in included:
            findings.update(check_page(flatten(rel, files), touched))
    return Report(sorted(findings), False)


def main() -> int:
    base_ref = os.environ.get("EL_BASE_REF", "").strip()
    globs = os.environ.get("EL_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("EL_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("EL_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("EL_WHOLE_TREE", False)
    report = run_check(base_ref, globs, ignores, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(f"{'::warning::' if base_ref else ''}Skipping the extracted-lemmas "
              f"check for this run ({reason}; not falling back to a whole-tree scan).")
        return 0
    for f in report.findings:
        print(f"::{'error' if fail else 'warning'} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("Every touched solution and proof cites a lemma for its general facts.")
        return 0
    print(f"\n{len(report.findings)} body(ies) stating a general fact without a lemma.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
