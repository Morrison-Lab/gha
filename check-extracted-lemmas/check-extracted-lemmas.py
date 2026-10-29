#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a general fact that a proof, solution or example states instead of citing a lemma.

The lab's rule (Ezra, 2026-10-29; psw ``chapters/teaching.qmd``): extract a lemma
wherever feasible. A general fact that does not depend on its setting (for example
``E[Z^2] = Var(Z) + (E Z)^2`` for any random variable ``Z``) goes in its own
``#lem-`` div on the site that owns the topic, and the proof, solution or example
that uses it links to the lemma.

The check reads the body of

- each ``#sol-`` and ``#exm-`` div, and
- the proof of each ``#thm-``, ``#lem-``, ``#cor-`` or ``#prp-`` div (a ``.proof``
  div nested in it or directly after it),

and flags a body whose prose states a fact for ``any``, ``every`` or ``all`` of
something, in a sentence that also holds math, when the body cites no result
(``@thm-``, ``@lem-``, ``@cor-``, ``@prp-``, or a link to a ``#thm-``, ``#lem-``,
``#cor-`` or ``#prp-`` anchor). A theorem's own statement is not read, since a
theorem is meant to be general.

The check follows ``{{< include ... >}}`` lines, so a page is read in the order a
reader sees it. It is a heuristic: it is warn-only by default, and
``<!-- lemma-ok: reason -->`` in the body exempts it.

A body is checked when the diff adds a line inside it, or always with
``EL_WHOLE_TREE=true``. No base-ref means the run is skipped.

Configuration (environment variables, set by the composite action):
  EL_BASE_REF      Git ref/SHA to diff against; empty and not whole-tree => skip.
  EL_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  EL_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  EL_FAIL          "true" => blocking; default "false" (warning annotations).
  EL_WHOLE_TREE    "true" => check every body in the tree.
"""

import os
import posixpath
import re
import subprocess
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = False
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
COMMENT_RE = re.compile(r"<!--.*?--!?>", re.DOTALL)
GENERAL_RE = re.compile(r"\bfor\s+(?:any|every|all)\b", re.IGNORECASE)
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
        raw = COMMENT_RE.sub("", raw)
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


def states_general_fact(text: str) -> bool:
    """A sentence with 'for any/every/all' that also holds inline math."""
    for sentence in SENTENCE_END_RE.split(text):
        if GENERAL_RE.search(sentence) and "$" in sentence:
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
    """Findings for the solution, example and proof bodies of one flattened page."""
    findings: List[Finding] = []
    bodies: List[Tuple[str, int, int]] = []  # (ident, first stream index, last)
    for d in find_divs(stream):
        kind = d.ident.split("-", 1)[0]
        if kind in ("sol", "exm"):
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

def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff: str) -> Dict[str, Set[int]]:
    """Added, non-blank line numbers per path."""
    added: Dict[str, Set[int]] = {}
    path: Optional[str] = None
    old_left = new_left = new_line = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("+"):
                if path is not None and line[1:].strip():
                    added[path].add(new_line)
                new_line += 1
                new_left -= 1
            elif line.startswith("-"):
                old_left -= 1
            continue
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = None if target == "/dev/null" else (
                target[2:] if target.startswith("b/") else target)
            if path is not None:
                added.setdefault(path, set())
            continue
        m = _HUNK_RE.match(line)
        if m:
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_line = int(m.group(2))
            new_left = int(m.group(3)) if m.group(3) is not None else 1
    return added


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
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], True)
        touched = parse_diff(diff)
    files: Dict[str, List[str]] = {}
    for rel in names:
        content = _read_lines(rel)
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
    ignores = compile_ignores(_split_list(os.environ.get("EL_PATHS_IGNORE", "")))
    fail = _env_flag("EL_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("EL_WHOLE_TREE", False)
    report = run_check(base_ref, globs, ignores, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(f"{'::warning::' if base_ref else ''}Skipping the extracted-lemmas "
              f"check for this run ({reason}; not falling back to a whole-tree scan).")
        return 0
    for f in report.findings:
        print(f"::{'error' if fail else 'warning'} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("Every touched solution, example and proof cites a lemma for its general facts.")
        return 0
    print(f"\n{len(report.findings)} body(ies) stating a general fact without a lemma.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
