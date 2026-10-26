#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Keep warnings and non-output messages out of rendered code.

The lab's rule (Ezra, 2026-10-26): code in the notes shows its output and
nothing else, so a render prints no warning and no message. The commonest
case is ggplot2's ``geom_smooth()`` using formula 'y ~ x'`` message, which
disappears when the call names its ``formula``. Two checks, one per way the
rule is broken:

**Source lint** (``CCM_GLOBS``). Flags a call that is known to print a
message unless it is given an argument:

- ``geom_smooth()`` or ``stat_smooth()`` with no ``formula`` argument;
- ``geom_histogram()`` or ``stat_bin()`` with none of ``bins``, ``binwidth``
  and ``breaks`` (the "using bins = 30" message).

In a ``.qmd``, ``.Rmd`` or ``.md`` file only the lines of R code chunks are
read, so prose and inline code that name these functions are not flagged; a
``.R`` file is read in full.

The call is read across lines up to its closing parenthesis, outside strings
and comments. Diff-scoped by default: only a call that spans a line added
since ``CCM_BASE_REF`` is reported, so a corpus's existing calls are not
reflagged. ``CCM_WHOLE_TREE=true`` scans every tracked file in full.

**Rendered output** (``CCM_SITE_DIR``). Scans the HTML of a rendered site for
Quarto's ``cell-output-stderr`` blocks, where knitr, reticulate and Jupyter put
every warning and message, and for the text of a few messages that arrive on
standard output. This is what catches the message no source rule predicted.
It always scans the whole site.

Configuration (environment variables, set by the composite action):
  CCM_BASE_REF     Git ref/SHA to diff against. Empty and not whole-tree =>
                   the source lint skips with a warning.
  CCM_GLOBS        Space-separated git pathspecs for the source lint
                   (default: '*.qmd *.Rmd *.R').
  CCM_WHOLE_TREE   "true" => lint every tracked matching file in full.
  CCM_SITE_DIR     Directory of rendered HTML to scan. Empty => skip.
  CCM_SITE_IGNORE  Comma/newline-separated glob patterns, relative to the
                   site directory, to skip.
  CCM_FAIL         "true" => exit 1 on a finding; default "false" => warning
                   annotations only.
"""

import fnmatch
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

DEFAULT_GLOBS = "*.qmd *.Rmd *.R"


class Rule(NamedTuple):
    functions: Tuple[str, ...]
    required: Tuple[str, ...]  # at least one of these arguments
    message: str


RULES = (
    Rule(("geom_smooth", "stat_smooth"), ("formula",),
         "`{fn}()` with no `formula` prints \"`geom_smooth()` using formula "
         "'y ~ x'\"; add `formula = y ~ x` (or the formula you mean)"),
    Rule(("geom_histogram", "stat_bin"), ("bins", "binwidth", "breaks"),
         "`{fn}()` with no `bins`, `binwidth` or `breaks` prints "
         "\"`stat_bin()` using `bins = 30`\"; choose and name the bins"),
)

CALL_RE = re.compile(
    r"(?<![\w.])(?:ggplot2::)?(" +
    "|".join(f for r in RULES for f in r.functions) + r")\s*\(")


def call_spans(text: str) -> List[Tuple[int, int, str, str]]:
    """(first line, last line, function, argument text) of each rule call.

    Lines are 1-based. The argument text runs to the matching parenthesis,
    skipping parentheses in strings and ``#`` comments.
    """
    out = []
    starts = [0]
    for m in re.finditer("\n", text):
        starts.append(m.end())

    def line_of(pos: int) -> int:
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    for m in CALL_RE.finditer(text):
        depth, i, quote = 1, m.end(), ""
        while i < len(text) and depth:
            c = text[i]
            if quote:
                if c == "\\":
                    i += 1
                elif c == quote:
                    quote = ""
            elif c in "\"'`":
                quote = c
            elif c == "#":
                nl = text.find("\n", i)
                i = len(text) if nl < 0 else nl
                continue
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            i += 1
        if depth == 0:
            out.append((line_of(m.start()), line_of(i - 1), m.group(1),
                        text[m.end():i - 1]))
    return out


FENCE_OPEN_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})\s*\{?\s*(\w*)")


def code_only(text: str) -> str:
    """Blank every line outside an R code chunk, keeping the line numbers.

    Prose and inline code that merely name ``geom_smooth()`` are not calls.
    """
    out, fence, is_r = [], "", False
    for line in text.split("\n"):
        m = FENCE_OPEN_RE.match(line)
        if fence:
            if m and line.strip().startswith(fence) and not m.group(2):
                fence = ""
                out.append("")
            else:
                out.append(line if is_r else "")
        elif m:
            fence, is_r = m.group(1), m.group(2).lower() in ("r", "rscript")
            out.append("")
        else:
            out.append("")
    return "\n".join(out)


def lint_text(text: str, added: Optional[Set[int]] = None
              ) -> List[Tuple[int, str]]:
    """Findings (line, message); only calls touching ``added`` if given."""
    findings = []
    for first, last, fn, args in call_spans(text):
        if added is not None and not any(first <= n <= last for n in added):
            continue
        for rule in RULES:
            if fn in rule.functions and not any(
                    re.search(rf"(?<![\w.]){a}\s*=(?!=)", args)
                    for a in rule.required):
                findings.append((first, rule.message.format(fn=fn)))
    return findings


# -- Rendered output -----------------------------------------------------------

STDERR_RE = re.compile(r'class="[^"]*\bcell-output-stderr\b[^"]*"')
TEXT_RES = (
    re.compile(r"`geom_smooth\(\)` using (?:formula|method)"),
    re.compile(r"`stat_bin\(\)` using `bins = 30`"),
)
TAG_RE = re.compile(r"<[^>]+>")


def scan_html(html: str) -> List[Tuple[int, str]]:
    findings = []
    lines = html.split("\n")
    last_block = -2
    for n, line in enumerate(lines, 1):
        if STDERR_RE.search(line):
            # The block's text follows its opening tag, here or on the next line.
            snippet = TAG_RE.sub("", " ".join(lines[n - 1:n + 1])).strip()
            findings.append((n, "warning or message block in rendered "
                             f"output: {snippet[:100]}"))
            last_block = n
            continue
        if n - last_block <= 1:
            continue  # the text of a block already reported
        plain = TAG_RE.sub("", line)
        for rx in TEXT_RES:
            if rx.search(plain):
                findings.append((n, f"message text in rendered output: "
                                 f"{plain.strip()[:100]}"))
                break
    return findings


# -- Git plumbing ----------------------------------------------------------------

def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace")
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def added_lines(diff: str) -> Dict[str, Set[int]]:
    out: Dict[str, Set[int]] = {}
    path: Optional[str] = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            t = line[4:].rstrip("\t")
            path = None if t == "/dev/null" else t[2:] if t.startswith("b/") else t
            if path:
                out.setdefault(path, set())
            continue
        m = _HUNK_RE.match(line)
        if m and path:
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            out[path].update(range(start, start + count))
    return out


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value in ("1", "true", "yes", "on")


def _read(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as h:
            return h.read()
    except OSError:
        return None


def source_findings(base_ref: str, globs: List[str], whole_tree: bool
                    ) -> Optional[Tuple[List[Tuple[str, int, str]], int]]:
    """Findings and files read, or None when the diff cannot be computed."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return None
        wanted = {p: None for p in out.splitlines() if p}
    else:
        if not base_ref:
            return None
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if not base or not base.strip():
            return None
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return None
        wanted = dict(added_lines(diff))
    findings, files = [], 0
    for rel in sorted(wanted):
        text = _read(rel)
        if text is None:
            continue
        files += 1
        if not rel.endswith(".R"):
            text = code_only(text)
        findings += [(rel, n, msg) for n, msg in lint_text(text, wanted[rel])]
    return findings, files


def site_findings(site_dir: str, ignores: List[str]
                  ) -> Tuple[List[Tuple[str, int, str]], int]:
    findings, files = [], 0
    for root, _dirs, names in os.walk(site_dir):
        for name in sorted(names):
            if not name.endswith(".html"):
                continue
            rel = os.path.relpath(os.path.join(root, name), site_dir)
            rel = rel.replace(os.sep, "/")
            if any(fnmatch.fnmatch(rel, p) for p in ignores):
                continue
            html = _read(os.path.join(root, name))
            if html is None:
                continue
            files += 1
            findings += [(rel, n, msg) for n, msg in scan_html(html)]
    return findings, files


def main() -> int:
    base_ref = os.environ.get("CCM_BASE_REF", "").strip()
    globs = os.environ.get("CCM_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    whole_tree = _env_flag("CCM_WHOLE_TREE", False)
    site_dir = os.environ.get("CCM_SITE_DIR", "").strip()
    ignores = [p.strip() for p in re.split(r"[,\n]", os.environ.get("CCM_SITE_IGNORE", "")) if p.strip()]
    fail = _env_flag("CCM_FAIL", False)
    level = "error" if fail else "warning"
    total = 0

    src = source_findings(base_ref, globs, whole_tree)
    if src is None:
        why = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(f"{'::warning::' if base_ref else ''}Skipping the source lint ({why}).")
    else:
        findings, files = src
        for rel, n, msg in findings:
            print(f"::{level} file={rel},line={n}::{msg}")
        total += len(findings)
        print(f"Source lint: {files} file(s) read, {len(findings)} finding(s).")

    if site_dir:
        findings, files = site_findings(site_dir, ignores)
        if files == 0:
            print(f"::{level}::No HTML under '{site_dir}'; nothing rendered to scan.")
            total += 1
        for rel, n, msg in findings:
            print(f"::{level} file={site_dir}/{rel},line={n}::{msg}")
        total += len(findings)
        print(f"Rendered output: {files} page(s) scanned, {len(findings)} finding(s).")

    return 1 if fail and total else 0


if __name__ == "__main__":
    sys.exit(main())
