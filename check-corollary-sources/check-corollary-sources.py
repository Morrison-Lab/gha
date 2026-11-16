#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a corollary that names no earlier result.

The lab's rule (Ezra, 2026-11-16; psw ``chapters/defining-terms/using-theorem-environments.qmd``,
psw#668): a corollary is a result that follows directly from one earlier result,
and the corollary names that result in its statement or its proof.
A ``#cor-`` div whose statement and proof cite no result leaves the reader to
guess what it follows from, and is usually a proposition typed as a corollary.

A result citation is a cross-reference ``@thm-id``, ``@lem-id``, ``@cor-id`` or
``@prp-id`` (also inside brackets), or a Markdown link whose target ends in
``#thm-id``, ``#lem-id``, ``#cor-id`` or ``#prp-id``, on this site or another one.
The corollary's own id does not count. The check reads the corollary div and
its proof: a ``.proof`` div nested in it, or one that follows it directly,
with only blank lines between. A citation inside a comment or a code fence does
not count.

Whether a result is central (a theorem), smaller (a proposition) or a proof step
(a lemma) is a judgment no pattern can make, so the rest of psw's result-type
rule is a review item, not part of this check.

A corollary that follows from a definition or an axiom alone, and so has no
result to cite, is exempted with
``<!-- check-corollary-sources: allow: reason -->`` in the div or its proof.
A pragma with no reason does not exempt it. The check is warn-only by default.

A corollary is checked when the diff adds a line inside it or its proof, or
always with ``CCS_WHOLE_TREE=true``. No base-ref means the run is skipped.

Configuration (environment variables, set by the composite action):
  CCS_BASE_REF      Git ref/SHA to diff against; empty and not whole-tree => skip.
  CCS_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  CCS_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  CCS_FAIL          "true" => blocking; default "false" (warning annotations).
  CCS_WHOLE_TREE    "true" => check every corollary in the tree.
"""

import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

_ENGINE_PATH = Path(__file__).resolve().parent.parent / "check-write-idiom" / "check-write-idiom.py"
_spec = importlib.util.spec_from_file_location("check_write_idiom_engine", _ENGINE_PATH)
assert _spec is not None and _spec.loader is not None
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)

# The div reader and the git plumbing are check-definition-equations', so the
# checks cannot drift apart on fences, nested divs or the diff model.
_DE_PATH = Path(__file__).resolve().parent.parent / "check-definition-equations" / "check-definition-equations.py"
_de_spec = importlib.util.spec_from_file_location("check_definition_equations_base", _DE_PATH)
assert _de_spec is not None and _de_spec.loader is not None
base = importlib.util.module_from_spec(_de_spec)
_de_spec.loader.exec_module(base)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = False

ADVICE = (
    "name the result the corollary follows from, as @thm-..., @lem-..., "
    "@cor-..., @prp-... or [text](page.qmd#thm-...), in its statement or "
    "its proof; if it follows from no result, retype it as a proposition "
    "(#prp-), or add <!-- check-corollary-sources: allow: reason -->"
)

ID_RE = re.compile(r"#(cor-[A-Za-z0-9_-]+)")
# The pragma counts only with a reason after "allow:".
ALLOW_RE = re.compile(r"<!--\s*check-corollary-sources:\s*allow\s*:\s*(?!-->)\S", re.IGNORECASE)
RESULT_REF_RE = re.compile(r"(?<![\w/.#-])@((?:thm|lem|cor|prp)-[A-Za-z0-9_-]*[A-Za-z0-9_])")
RESULT_LINK_RE = re.compile(r"\]\([^)\s]*#((?:thm|lem|cor|prp)-[A-Za-z0-9_-]*[A-Za-z0-9_])[^)]*\)")
PROOF_OPEN_RE = re.compile(r"(?:^|[\s{])\.?proof\b")


class Finding(NamedTuple):
    path: str
    line: int
    message: str


def find_divs(lines: List[str]):
    """Outermost divs with a ``cor-`` id, outside code fences."""
    saved = base.ID_RE
    base.ID_RE = ID_RE
    try:
        return base.find_divs(lines)
    finally:
        base.ID_RE = saved


def following_proof(lines: List[str], end: int) -> Optional[Tuple[int, int]]:
    """The (open, close) line indices of a proof div right after line ``end``.

    Only blank lines may separate the corollary's closing fence from the proof.
    """
    idx = end + 1
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines):
        return None
    dm = base.DIV_RE.match(lines[idx])
    if not dm or not dm.group(2) or "#" in dm.group(2):
        return None
    depth = 0
    close = None
    for j in range(idx, len(lines)):
        m = base.DIV_RE.match(lines[j])
        if not m:
            continue
        if m.group(2):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                close = j
                break
    if close is None:
        return None
    # A proof, or a wrapper with no id (such as `.content-hidden`) that holds one.
    if PROOF_OPEN_RE.search(dm.group(2)):
        return idx, close
    for j in range(idx + 1, close):
        m = base.DIV_RE.match(lines[j])
        if m and m.group(2) and PROOF_OPEN_RE.search(m.group(2)):
            return idx, close
    return None


def cites_result(text: str, own: str) -> bool:
    """Whether the text cites a result other than ``own``."""
    for rx in (RESULT_REF_RE, RESULT_LINK_RE):
        for m in rx.finditer(text):
            if m.group(1) != own:
                return True
    return False


def check_file(path: str, lines: List[str],
               touched: Optional[Set[int]]) -> List[Finding]:
    findings: List[Finding] = []
    for d in find_divs(lines):
        last = d.end
        body = list(d.body)
        proof = following_proof(lines, d.end)
        if proof is not None:
            body.extend(lines[proof[0]:proof[1] + 1])
            last = proof[1]
        if touched is not None and not any(n + 1 in touched
                                           for n in range(d.start, last + 1)):
            continue
        if any(ALLOW_RE.search(line) for line in body):
            continue
        text = base.mdmask.replace_comments(base.strip_fences(tuple(body)), " ", bang=True)
        if cites_result(text, d.ident):
            continue
        findings.append(Finding(path, d.start + 1,
            f"#{d.ident}: the corollary names no earlier result. A corollary "
            f"follows directly from an earlier result and names it. Fix: {ADVICE}"))
    return findings


class Report(NamedTuple):
    findings: List[Finding]
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    out = base._run_git(["ls-files", "--", *globs])
    if out is None:
        return Report([], True)
    names = [r for r in out.splitlines()
             if r and not any(g.match(r) for g in ignores)]
    touched: Optional[Dict[str, Set[int]]] = None
    if not whole_tree:
        if not base_ref:
            return Report([], True)
        merge_base = base._run_git(["merge-base", base_ref, "HEAD"])
        if merge_base is None or not merge_base.strip():
            return Report([], True)
        diff = base._run_git([*engine.GIT_DIFF_ARGS, merge_base.strip(), "--", *globs])
        if diff is None:
            return Report([], True)
        touched = base.parse_diff(diff)
    findings: List[Finding] = []
    for rel in names:
        if touched is not None and not touched.get(rel):
            continue
        content = base._read_lines(rel)
        if content is not None:
            findings.extend(check_file(rel, content,
                                       None if touched is None else touched[rel]))
    return Report(sorted(findings), False)


def main() -> int:
    base_ref = os.environ.get("CCS_BASE_REF", "").strip()
    globs = os.environ.get("CCS_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = base.compile_ignores(base._split_list(os.environ.get("CCS_PATHS_IGNORE", "")))
    fail = base._env_flag("CCS_FAIL", _DEFAULT_FAIL)
    whole_tree = base._env_flag("CCS_WHOLE_TREE", False)
    report = run_check(base_ref, globs, ignores, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(f"{'::warning::' if base_ref else ''}Skipping the corollary-sources "
              f"check for this run ({reason}; not falling back to a whole-tree scan).")
        return 0
    for f in report.findings:
        print(f"::{'error' if fail else 'warning'} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("Every touched corollary names an earlier result.")
        return 0
    print(f"\n{len(report.findings)} corollary div(s) that name no earlier result.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
