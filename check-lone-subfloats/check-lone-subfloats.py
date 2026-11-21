#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a figure or table that a reader sees with only one subfigure or subtable.

The lab's rule (Ezra, 2026-11-20; psw ``chapters/slides-posters-figures.qmd``,
"A figure with one panel has no subfigures"): a subfigure exists to be
compared with its siblings, so a figure whose reader sees one subfigure
labels a lone panel "(a)" and splits one caption into two. It is the figure
analog of the lone-heading rule (``check-heading-siblings``).

A float is a ``#fig-`` or ``#tbl-`` div. Its subfloats are the floats of the
same kind directly inside it:

- a nested ``#fig-``/``#tbl-`` div;
- a code chunk labeled ``#| label: fig-...`` (or ``tbl-...``);
- a Markdown image or table caption carrying ``{#fig-...}`` (``{#tbl-...}``).

A float is flagged when a reader sees exactly one of its subfloats:

- **One subfloat.** It holds one subfloat in all.
- **One per tab.** Its subfloats sit in the tabs of a tabset, such as a
  language tabset (``.panel-tabset group="language"``), so a tab shows one.
  Quarto still numbers them across the tabs, so the R tab shows a lone "(a)"
  and the Python tab a lone "(b)". This is what happens when a figure div
  wraps a language tabset whose chunks keep their ``fig-`` labels; drop the
  labels (keep ``fig-alt``), so the tabs are versions of one figure.

A code chunk is also flagged on its own when its ``fig-subcap`` or
``tbl-subcap`` lists exactly one subcaption, which makes a lone "(a)" too.

What is not counted: a float inside a code fence or an HTML comment, and the
content an ``include`` shortcode pulls in at render time (a float whose
subfloats come from an include is not seen).

``<!-- check-lone-subfloats: allow: <reason> -->`` inside the float's div, or
inside the chunk, exempts it. A pragma with no reason exempts nothing.

Design notes, in the model of ``check-exm-figures``, whose div and fence
parsing comes from ``check-one-div-per-subfile``:

- **Diff-scoped by default.** A float is reported when its span holds a line
  the diff adds. The whole file is parsed, since a div opens far above the
  line that changed. A moved line (deleted with the same text) is not new.
- **Skip, not fall back.** With no base ref, or an uncomputable diff, the
  check skips with a warning. ``CLS_WHOLE_TREE=true`` measures a corpus.
- **Fails by default** (``CLS_FAIL`` defaults to true).

Configuration (environment variables, set by the composite action):
  CLS_BASE_REF, CLS_GLOBS, CLS_PATHS_IGNORE, CLS_FAIL, CLS_WHOLE_TREE.
"""

import importlib.util
import itertools
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


ods = _load_sibling("check-one-div-per-subfile")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = True

# A float is a div whose own id is #fig- or #tbl-, not one whose attribute
# values merely mention such an id.
FLOAT_ID_RE = re.compile(r"(?:^|[\s{])#((fig|tbl)-[\w:.-]*)")
QUOTED_RE = re.compile(r"\"[^\"]*\"|'[^']*'")
# `.panel-tabset` as a class, or the bare Pandoc form `::: panel-tabset`.
TABSET_RE = re.compile(r"(?:^|[\s{])\.?panel-tabset\b")
CHUNK_OPEN_RE = re.compile(r"^[ \t]*(`{3,})\s*\{")
LABEL_RE = re.compile(r"^\s*#\|\s*label:\s*['\"]?((fig|tbl)-[\w:.-]*)")
SUBCAP_RE = re.compile(r"^\s*#\|\s*(fig|tbl)-subcap:\s*(.*?)\s*$")
LIST_ITEM_RE = re.compile(r"^\s*#\|\s+-\s+\S")
NO_OUTPUT_RE = re.compile(r"^\s*#\|\s*(?:include|output|eval):\s*false\s*$")
CHUNK_OPT_RE = re.compile(r"^\s*#\|\s*[\w.-]+\s*:")
INLINE_FLOAT_RE = re.compile(r"\{#(fig|tbl)-[\w:.-]*")
HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
ALLOW_RE = re.compile(r"<!--\s*check-lone-subfloats:\s*allow:\s*(?!-->)\S")

KIND_WORD = {"fig": ("figure", "subfigure"), "tbl": ("table", "subtable")}


class Finding(NamedTuple):
    line: int   # 1-based line the finding anchors to
    start: int  # span the diff must touch
    end: int
    ident: str
    kind: str   # "fig" or "tbl"
    rule: str   # "one", "per-tab" or "subcap"


_SERIAL = itertools.count()


class _Div:
    def __init__(self, start: int, attrs: str):
        self.start = start
        self.attrs = attrs
        m = FLOAT_ID_RE.search(QUOTED_RE.sub('""', attrs))
        self.kind = m.group(2) if m else None
        self.ident = "#" + m.group(1) if m else ""
        self.serial = next(_SERIAL)
        self.tabset = bool(TABSET_RE.search(attrs))
        self.tab_level: Optional[int] = None
        self.tab = -1  # index of the current tab, for a tabset
        self.allow = False
        # For a float: subfloats as (tabset path) tuples of (div id, tab).
        self.subs: List[Tuple[Tuple[int, int], ...]] = []


def _tab_path(stack: List["_Div"], upto: int) -> Tuple[Tuple[int, int], ...]:
    """The tabs, from stack index ``upto`` inward, that enclose the top.

    Content before a tabset's first tab heading shows above every tab,
    so that tabset does not narrow its view.
    """
    return tuple((d.serial, d.tab) for d in stack[upto + 1:]
                 if d.tabset and d.tab >= 0)


def _add_sub(stack: List["_Div"], kind: str) -> None:
    """Record a subfloat of ``kind`` in the innermost enclosing float."""
    for i in range(len(stack) - 1, -1, -1):
        d = stack[i]
        if d.kind is not None:
            if d.kind == kind:
                d.subs.append(_tab_path(stack, i))
            return


def _views(subs: List[Tuple[Tuple[int, int], ...]]) -> List[int]:
    """How many subfloats a reader sees, for each tab that holds one.

    A subfloat outside every tabset is always seen. For a subfloat in a tab,
    the view is that tab, with every other tabset on its best tab.
    """
    outside = sum(1 for p in subs if not p)
    by_tabset: Dict[int, Dict[int, int]] = {}
    for p in subs:
        if p:
            ts, tab = p[0]
            by_tabset.setdefault(ts, {}).setdefault(tab, 0)
            by_tabset[ts][tab] += 1
    views = []
    for ts, tabs in by_tabset.items():
        rest = sum(max(t.values()) for o, t in by_tabset.items() if o != ts)
        for count in tabs.values():
            views.append(outside + rest + count)
    return views


def _judge(d: "_Div", end: int) -> Optional[Finding]:
    if d.kind is None or d.allow or not d.subs:
        return None
    if len(d.subs) == 1:
        return Finding(d.start, d.start, end, d.ident, d.kind, "one")
    if any(v == 1 for v in _views(d.subs)):
        return Finding(d.start, d.start, end, d.ident, d.kind, "per-tab")
    return None


def _subcap_count(opts: List[str], idx: int) -> Optional[int]:
    """Entries in a ``fig-subcap``/``tbl-subcap`` option at ``opts[idx]``."""
    value = SUBCAP_RE.match(opts[idx]).group(2)
    if value:
        if value.startswith("["):
            inner = value.strip("[]").strip()
            if not inner:
                return 0
            return len(re.findall(r"\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^,]+", inner))
        return None  # a scalar such as `true`: Quarto counts the plots
    count = 0
    for line in opts[idx + 1:]:
        if LIST_ITEM_RE.match(line):
            count += 1
        elif CHUNK_OPT_RE.match(line) or not line.strip().startswith("#|"):
            break
    return count


def scan_file(lines: List[str]) -> List[Finding]:
    """Every lone-subfloat finding in a document, unscoped."""
    findings: List[Finding] = []
    stack: List[_Div] = []
    fence: Optional[Tuple[str, int]] = None
    chunk: Optional[Tuple[int, List[str]]] = None  # (start line, option lines)
    in_comment = False
    for idx, raw in enumerate(lines):
        n = idx + 1
        if fence is None and ALLOW_RE.search(raw):
            # The pragma exempts the innermost float around it,
            # even from inside a tabset or other div nested in that float.
            for d in reversed(stack):
                if d.kind is not None:
                    d.allow = True
                    break
        if fence is not None:
            if chunk is not None:
                chunk[1].append(raw)
            m = ods.FENCE_RE.match(raw)
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                if chunk is not None:
                    _close_chunk(chunk, n, stack, findings)
                fence = None
                chunk = None
            continue
        text, in_comment = ods.strip_comments(raw, in_comment)
        m = ods.FENCE_RE.match(text)
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            chunk = (n, []) if CHUNK_OPEN_RE.match(text) else None
            continue
        dm = ods.DIV_RE.match(text)
        if dm:
            if dm.group(2):
                d = _Div(n, dm.group(2))
                if d.kind is not None:
                    _add_sub(stack, d.kind)
                stack.append(d)
            elif stack:
                d = stack.pop()
                f = _judge(d, n)
                if f:
                    findings.append(f)
            continue
        hm = HEADING_RE.match(text)
        if hm and stack and stack[-1].tabset:
            ts = stack[-1]
            level = len(hm.group(1))
            if ts.tab_level is None:
                ts.tab_level = level
            if level == ts.tab_level:
                ts.tab += 1
            continue
        for im in INLINE_FLOAT_RE.finditer(text):
            _add_sub(stack, im.group(1))
    return sorted(findings)


def _close_chunk(chunk: Tuple[int, List[str]], end: int, stack: List[_Div],
                 findings: List[Finding]) -> None:
    start, body = chunk
    opts = []
    for line in body:
        if line.lstrip().startswith("#|"):
            opts.append(line)
        elif line.strip():
            break
    if any(ALLOW_RE.search(line) for line in body):
        return
    label = next((LABEL_RE.match(o) for o in opts if LABEL_RE.match(o)), None)
    if any(NO_OUTPUT_RE.match(o) for o in opts):
        return  # a chunk that shows nothing makes no subfloat
    if label:
        _add_sub(stack, label.group(2))
    for i, o in enumerate(opts):
        sm = SUBCAP_RE.match(o)
        if sm and _subcap_count(opts, i) == 1:
            ident = label.group(1) if label else "chunk"
            findings.append(Finding(start, start, end, ident, sm.group(1), "subcap"))


def format_message(f: Finding) -> str:
    noun, sub = KIND_WORD[f.kind]
    if f.rule == "subcap":
        return (f"Code chunk {f.ident} gives one {f.kind}-subcap, so its one "
                f"{noun} is labeled as a lone {sub} (a). Fix: drop the "
                f"{f.kind}-subcap and give the caption as {f.kind}-cap")
    if f.rule == "per-tab":
        return (f"The {noun} {f.ident} shows one {sub} in each tab of its "
                f"tabset, so each tab shows a lone {sub} such as (a) or (b). "
                f"Fix: drop the {f.kind}- labels of the chunks in the tabs "
                f"(keep {f.kind}-alt), so the tabs are versions of one {noun}")
    return (f"The {noun} {f.ident} holds one {sub}. Fix: give the {noun} more "
            f"{sub}s, or drop the {sub}'s {f.kind}- label so its content is "
            f"the {noun} itself")


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: list,
              whole_tree: bool) -> Report:
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = diffscope.git_paths(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, True)
        for rel in out:
            if rel and not diffscope.ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, True)
        diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                                  base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, True)
        added, deleted = diffscope.parse_diff(diff)
        for rel, numbered in added.items():
            if diffscope.ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, Finding]] = []
    files = lines = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        for f in scan_file(content):
            if keep is None or any(f.start <= n <= f.end for n in keep):
                findings.append((rel, f))
    return Report(findings, files, lines, False)


def main() -> int:
    base_ref = os.environ.get("CLS_BASE_REF", "").strip()
    globs = os.environ.get("CLS_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("CLS_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("CLS_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("CLS_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        if whole_tree:
            reason = "could not list the tracked files"
        elif base_ref:
            reason = f"could not diff against '{base_ref}'"
        else:
            reason = "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the lone-subfloat check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every figure the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.lines} line(s) across {report.files} file(s) "
          f"(scope: {scope}).")
    severity = "error" if fail else "warning"
    for rel, f in report.findings:
        print(f"::{severity} file={rel},line={f.line}::{format_message(f)}")
    if not report.findings:
        print("No examined figure or table shows a lone subfigure or subtable.")
        return 0
    print(f"\n{len(report.findings)} figure(s) or table(s) show a lone "
          "subfigure or subtable.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
