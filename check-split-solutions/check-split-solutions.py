#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a split exercise whose solution was not split with it.

The lab's rule (Ezra, 2026-10-28; Morrison-Lab/gha#1290): when a multi-part
exercise is split into separate ``#exr-`` divs, its solution is split the same
way, one ``#sol-`` per ``#exr-``, each with the slug of its exercise.

A *group* is the set of ``#exr-`` divs that share a slug once a trailing
``-partK`` is removed. A group with two or more exercises is *split*. In a
split group the check reports

- an exercise with no ``#sol-`` of the same slug, and a ``#sol-`` with no
  exercise of that slug;
- a solution that carries part labels: two lettered list items in one marker
  style (``(a)``/``(b)``, ``a.``/``b.``; a numbered list can be the answer),
  or a line opening "Part 2:";
- a solution holding a figure chunk (``label: fig-...`` or ``fig-cap``) when
  its own exercise does not ask for a plot but a sibling exercise does, since
  that solution then answers a sibling's question.

Ids may sit in different files (subfiles), so ids are indexed over every file
the globs match. A group is reported when the diff adds a line inside one of
its divs, or always with ``SSP_WHOLE_TREE=true``. A solution carrying
``<!-- split-solutions-ok: reason -->`` is exempt.

Configuration (environment variables, set by the composite action):
  SSP_BASE_REF      Git ref/SHA to diff against; empty and not whole-tree =>
                    skip the check.
  SSP_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  SSP_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  SSP_FAIL          "false" => warning annotations only; default "true".
  SSP_WHOLE_TREE    "true" => report every split group in the tree.
"""

import os
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
_DEFAULT_FAIL = True

ADVICE = (
    "give each #exr- its own #sol- of the same slug, in its own subfile, "
    "with only the code and prose that answer that exercise"
)

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
ID_RE = re.compile(r"#((?:exr|sol)-[A-Za-z0-9_-]+)")
PART_RE = re.compile(r"-part\d+$")
ALLOW_RE = re.compile(r"<!--\s*split-solutions-ok\b", re.IGNORECASE)
COMMENT_RE = re.compile(r"<!--.*?--!?>", re.DOTALL)
MARKER_RE = re.compile(
    r"^[ \t]*(?:>\s*)*(?:\*\*|__)?"
    r"(?:\((?P<paren>[A-Za-z]|[ivx]{2,}|\d{1,2})\)|(?P<dot>[a-z]|\d{1,2})(?P<end>[.)]))"
    r"(?:\*\*|__)?\s+\S"
)
PART_LINE_RE = re.compile(
    r"^[ \t]*(?:\*\*|__)?Part\s+(?:\d+|[a-z])\s*(?:\*\*|__)?\s*[:.)—-]",
    re.IGNORECASE)
FIGURE_RE = re.compile(r"^#\|\s*(?:label:\s*fig-|fig-cap\b)", re.MULTILINE)
PLOT_RE = re.compile(
    r"\b(?:plot|plots|draw|sketch|graph|scatter\s*plot|histogram|figure|chart|"
    r"visuali[sz]e)\b", re.IGNORECASE)


class Div(NamedTuple):
    ident: str
    path: str
    start: int  # 1-based line of the opening fence
    end: int  # 1-based line of the closing fence
    body: Tuple[str, ...]


def find_divs(path: str, lines: List[str]) -> List[Div]:
    """Outermost ``exr-``/``sol-`` divs outside code fences."""
    fence: Optional[Tuple[str, int]] = None
    depth = 0
    cur: Optional[Tuple[int, str, int]] = None
    found: List[Div] = []
    for idx, raw in enumerate(lines):
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
                cur = (idx + 1, im.group(1), depth)
            depth += 1
        elif depth > 0:
            depth -= 1
            if cur is not None and depth == cur[2]:
                found.append(Div(cur[1], path, cur[0], idx + 1,
                                 tuple(lines[cur[0]:idx])))
                cur = None
    if cur is not None:
        found.append(Div(cur[1], path, cur[0], len(lines) + 1,
                         tuple(lines[cur[0]:])))
    return found


def prose_lines(body: Tuple[str, ...]) -> List[str]:
    """Body lines outside code fences, display math and comments."""
    out: List[str] = []
    fence: Optional[Tuple[str, int]] = None
    in_math = False
    for raw in body:
        raw = COMMENT_RE.sub("", raw)
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if raw.count("$$") % 2:
            in_math = not in_math
            continue
        if in_math or "$$" in raw:
            continue
        out.append(raw)
    return out


def part_labels(body: Tuple[str, ...]) -> bool:
    """Whether a solution body labels several parts."""
    styles: Dict[str, int] = {}
    for line in prose_lines(body):
        if PART_LINE_RE.match(line):
            return True
        m = MARKER_RE.match(line)
        if m:
            label = m.group("paren") or m.group("dot")
            style = "paren" if m.group("paren") else "dot" + m.group("end")
            if not label.isdigit():  # a numbered list can be the answer itself
                styles[style] = styles.get(style, 0) + 1
    return any(n > 1 for n in styles.values())


def asks_for_plot(div: Div) -> bool:
    return any(PLOT_RE.search(line) for line in prose_lines(div.body))


def has_figure(div: Div) -> bool:
    return bool(FIGURE_RE.search("\n".join(div.body)))


def slug(ident: str) -> str:
    return ident.split("-", 1)[1]


def group_of(ident: str) -> str:
    return PART_RE.sub("", slug(ident))


class Finding(NamedTuple):
    path: str
    line: int
    message: str


def check_groups(divs: List[Div]) -> Dict[str, List[Finding]]:
    """Findings per group key, for every split group in ``divs``."""
    exr: Dict[str, Div] = {}
    sol: Dict[str, Div] = {}
    for d in divs:
        (exr if d.ident.startswith("exr-") else sol)[slug(d.ident)] = d
    groups: Dict[str, List[str]] = {}
    for s in exr:
        groups.setdefault(PART_RE.sub("", s), []).append(s)
    result: Dict[str, List[Finding]] = {}
    for key, members in groups.items():
        if len(members) < 2:
            continue
        found: List[Finding] = []
        for s in sorted(members):
            e = exr[s]
            if s not in sol:
                found.append(Finding(e.path, e.start,
                    f"#exr-{s} is one of {len(members)} split exercises but has no "
                    f"#sol-{s}. Fix: {ADVICE}"))
        for s, d in sol.items():
            if PART_RE.sub("", s) != key or any(ALLOW_RE.search(x) for x in d.body):
                continue
            if s not in exr:
                found.append(Finding(d.path, d.start,
                    f"#sol-{s} has no #exr-{s} in a split group. Fix: {ADVICE}"))
                continue
            if part_labels(d.body):
                found.append(Finding(d.path, d.start,
                    f"#sol-{s} labels several parts, but its exercise is split. "
                    f"Fix: {ADVICE}"))
            siblings = [exr[m] for m in members if m != s]
            if (has_figure(d) and not asks_for_plot(exr[s])
                    and any(asks_for_plot(x) for x in siblings)):
                found.append(Finding(d.path, d.start,
                    f"#sol-{s} draws a figure that a sibling exercise asks for, "
                    f"not its own. Fix: {ADVICE}"))
        if found:
            result[key] = found
    return result


# -- Git plumbing ------------------------------------------------------------

def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff: str) -> Tuple[Dict[str, Set[int]], Set[str]]:
    """Added line numbers per path, and the set of deleted texts."""
    added: Dict[str, Dict[int, str]] = {}
    deleted: Set[str] = set()
    path: Optional[str] = None
    old_left = new_left = new_line = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("+"):
                if path is not None:
                    added[path][new_line] = line[1:]
                new_line += 1
                new_left -= 1
            elif line.startswith("-"):
                deleted.add(line[1:])
                old_left -= 1
            continue
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = None if target == "/dev/null" else (
                target[2:] if target.startswith("b/") else target)
            if path is not None:
                added.setdefault(path, {})
            continue
        m = _HUNK_RE.match(line)
        if m:
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_line = int(m.group(2))
            new_left = int(m.group(3)) if m.group(3) is not None else 1
    return ({p: {n for n, t in d.items() if t.strip() and t not in deleted}
             for p, d in added.items()}, deleted)


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
    groups: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    out = _run_git(["ls-files", "--", *globs])
    if out is None:
        return Report([], 0, True)
    files = [r for r in out.splitlines()
             if r and not any(g.match(r) for g in ignores)]
    touched: Optional[Dict[str, Set[int]]] = None
    if not whole_tree:
        if not base_ref:
            return Report([], 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, True)
        touched = parse_diff(diff)[0]
    divs: List[Div] = []
    for rel in files:
        content = _read_lines(rel)
        if content is not None:
            divs.extend(find_divs(rel, content))
    by_group: Dict[str, List[Div]] = {}
    for d in divs:
        by_group.setdefault(group_of(d.ident), []).append(d)
    per_group = check_groups(divs)
    findings: List[Finding] = []
    for key, found in per_group.items():
        if touched is not None and not any(
                n in touched.get(d.path, ()) for d in by_group[key]
                for n in range(d.start, d.end + 1)):
            continue
        findings.extend(found)
    return Report(sorted(findings), len(per_group), False)


def main() -> int:
    base_ref = os.environ.get("SSP_BASE_REF", "").strip()
    globs = os.environ.get("SSP_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("SSP_PATHS_IGNORE", "")))
    fail = _env_flag("SSP_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("SSP_WHOLE_TREE", False)
    report = run_check(base_ref, globs, ignores, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(f"{'::warning::' if base_ref else ''}Skipping the split-solutions "
              f"check for this run ({reason}; not falling back to a whole-tree scan).")
        return 0
    severity = "error" if fail else "warning"
    for f in report.findings:
        print(f"::{severity} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("Every touched split exercise has its solution split with it.")
        return 0
    print(f"\n{len(report.findings)} finding(s) in {report.groups} split group(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
