#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a derivation solution whose result is never restated as a theorem.

The lab's rule (Ezra, 2026-10-29; psw ``chapters/teaching.qmd``): a result first
derived in an exercise solution is then restated in its own theorem-type div
(``#thm-``, ``#lem-``, ``#cor-`` or ``#prp-``) after the exercise, so a reader
finds it stated apart from its working.

A ``#sol-`` div is *a derivation* when

- its exercise asks to derive, prove, show, solve, simplify, express or find an
  expression, formula or closed form, and does not cite an existing result
  (``@thm-...``), which would make the solution a proof of a stated result; and
- the solution displays an equation.

The check follows ``{{< include ... >}}`` lines, so a page is read in the order a
reader sees it. After a derivation solution, a theorem-type div has to appear
before the next exercise of a different group (a group is the exercise slug
with a trailing ``-partK`` removed). The check is a heuristic: it is
warn-only by default, and ``<!-- restated-ok: reason -->`` in the solution
exempts it.

A restating theorem is also flagged when its proof (a nested or directly
following ``.proof`` div) cites a solution (``@sol-...``) and displays no
equation of its own, since a proof that only points back at the solution leaves
the result unproved where it is stated. ``<!-- restated-ok: reason -->`` in the
theorem or its proof exempts it. Undefined symbols stay a review item.

A solution is checked when the diff adds a line inside it or its exercise, and
a proof when the diff adds a line inside the theorem or its proof, or
always with ``RR_WHOLE_TREE=true``. No base-ref means the run is skipped.

Configuration (environment variables, set by the composite action):
  RR_BASE_REF      Git ref/SHA to diff against; empty and not whole-tree => skip.
  RR_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  RR_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  RR_FAIL          "true" => blocking; default "false" (warning annotations).
  RR_WHOLE_TREE    "true" => check every derivation solution in the tree.
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
    "restate the result in its own #thm-, #lem-, #cor- or #prp- div after the "
    "exercise, or add <!-- restated-ok: reason --> to the solution"
)

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
ID_RE = re.compile(r"#((?:exr|sol|thm|lem|cor|prp)-[A-Za-z0-9_-]+)")
INCLUDE_RE = re.compile(r"\{\{<\s*include\s+(\S+?)\s*>\}\}")
PART_RE = re.compile(r"-part\d+$")
ALLOW_RE = re.compile(r"<!--\s*restated-ok\b", re.IGNORECASE)
COMMENT_RE = re.compile(r"<!--.*?--!?>", re.DOTALL)
DERIVE_RE = re.compile(
    r"\b(?:derive|derivation|prove|show\s+that|show\s+how|solve\s+for|simplify|"
    r"express|closed\s+form|(?:find|obtain|give|write\s+down)\s+(?:an?\s+|the\s+)?"
    r"(?:expression|formula|equation|form))\b", re.IGNORECASE)
CITES_RESULT_RE = re.compile(r"@(?:thm|lem|cor|prp)-")
CITES_SOLUTION_RE = re.compile(r"@sol-")
PROOF_OPEN_RE = re.compile(r"^ {0,3}:{3,}\s*\{[^}]*\.proof\b")
PROOF_ADVICE = (
    "derive the result in the proof from earlier results, or add "
    "<!-- restated-ok: reason --> to the theorem"
)


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
    """Outermost divs with an exr/sol/thm/lem/cor/prp id, outside code fences."""
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
    out: List[str] = []
    fence = False
    for raw in body:
        raw = COMMENT_RE.sub("", raw)
        if FENCE_RE.match(raw):
            fence = not fence
            continue
        if not fence:
            out.append(raw)
    return " ".join(out)


def displays_equation(body: Tuple[str, ...]) -> bool:
    text = "\n".join(body)
    return "$$" in text or "\\begin{align" in text


def slug(ident: str) -> str:
    return ident.split("-", 1)[1]


def group_of(ident: str) -> str:
    return PART_RE.sub("", slug(ident))


def is_derivation(sol: Div, exr: Div) -> bool:
    if any(ALLOW_RE.search(line) for line in sol.body):
        return False
    ask = prose(exr.body)
    return (bool(DERIVE_RE.search(ask)) and not CITES_RESULT_RE.search(ask)
            and displays_equation(sol.body))


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


def check_proof(stream: Stream, thm: Div,
                touched: Optional[Dict[str, Set[int]]]) -> List[Finding]:
    """A restating theorem whose proof only cites a solution."""
    span = proof_span(stream, thm)
    if span is None:
        return []
    proof = tuple(t for _, _, t in stream[span[0]:span[1] + 1])
    if any(ALLOW_RE.search(t) for t in thm.body + proof):
        return []
    if not CITES_SOLUTION_RE.search(prose(proof)) or displays_equation(proof):
        return []
    lines = stream[thm.start:thm.end + 1] + stream[span[0]:span[1] + 1]
    if touched is not None and not any(ln in touched.get(p, ()) for p, ln, _ in lines):
        return []
    path, line, _ = stream[thm.start]
    return [Finding(path, line,
        f"#{thm.ident} is proved only by citing a solution, with no derivation of "
        f"its own (heuristic). Fix: {PROOF_ADVICE}")]


def check_page(stream: Stream, touched: Optional[Dict[str, Set[int]]]) -> List[Finding]:
    divs = find_divs(stream)
    findings: List[Finding] = []

    def hit(*ds: Div) -> bool:
        if touched is None:
            return True
        return any(ln in touched.get(p, ()) for d in ds
                   for p, ln, _ in stream[d.start:d.end + 1])

    for i, d in enumerate(divs):
        if not d.ident.startswith("sol-"):
            continue
        exr = next((x for x in reversed(divs[:i])
                    if x.ident == "exr-" + slug(d.ident)), None)
        if exr is None or not is_derivation(d, exr):
            continue
        group = group_of(d.ident)
        restated = False
        for nxt in divs[i + 1:]:
            kind = nxt.ident.split("-", 1)[0]
            if kind in RESULT_KINDS:
                restated = True
                findings.extend(check_proof(stream, nxt, touched))
                break
            if kind == "exr" and group_of(nxt.ident) != group:
                break
        if not restated and hit(d, exr):
            path, line, _ = stream[d.start]
            findings.append(Finding(path, line,
                f"#{d.ident} derives a result, but no #thm-, #lem-, #cor- or #prp- div "
                f"restates it after the exercise (heuristic). Fix: {ADVICE}"))
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
    base_ref = os.environ.get("RR_BASE_REF", "").strip()
    globs = os.environ.get("RR_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("RR_PATHS_IGNORE", "")))
    fail = _env_flag("RR_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("RR_WHOLE_TREE", False)
    report = run_check(base_ref, globs, ignores, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(f"{'::warning::' if base_ref else ''}Skipping the restated-results "
              f"check for this run ({reason}; not falling back to a whole-tree scan).")
        return 0
    for f in report.findings:
        print(f"::{'error' if fail else 'warning'} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("Every touched derivation solution has its result restated as a theorem.")
        return 0
    print(f"\n{len(report.findings)} derivation solution(s) without a restated result.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
