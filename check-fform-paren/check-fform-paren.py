#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag ``\name\paren{...}`` (or ``\sb{``, ``\cb{``) where ``\namef{...}`` exists.

The lab's rule (Morrison-Lab/gha#1082, companion to Morrison-Lab/ai-config#4597):
when a macro ``\name`` has an f form ``\namef`` that takes the argument in
braces, write ``\namef{...}``, not ``\name\paren{...}``. The rule alone failed
at composition time in Morrison-Lab/sds#261, where ``\fitproc\paren{...}`` was
typed by hand although ``\fitprocf`` existed.

The known f forms are read from a macros file (``CFP_MACROS_FILE``, default
``latex-macros/macros.qmd``): every ``\providecommand{\XXXf}`` and
``\newcommand{\XXXf}`` names one. When the file is missing the check skips with
a warning, since without it no f form is known.

What is flagged: in ``.qmd``, ``.md`` and ``.Rmd`` files, a macro ``\name``
immediately followed by ``\paren{``, ``\sb{`` or ``\cb{`` (the ``DELIMITERS``
constant) when ``\namef`` is a known f form. The message is
``\name\paren{...} -> \namef{...}``, with ``\sb`` or ``\cb`` in place of
``\paren`` when that is what was written.

What is not flagged:

- a delimiter macro with no macro directly before it;
- a macro with no f form (``\foo\paren{x}`` when ``\foof`` is not defined);
- code fences and code spans, HTML comments, and YAML front matter;
- a line carrying, or following, ``<!-- check-fform-paren: allow -->``.

Design notes, in the model of ``check-literal-math-letters`` and
``check-local-macros``:

- **Diff-scoped by default.** Only lines *added* since ``CFP_BASE_REF`` are
  reported. An added line whose exact text was also deleted in the same diff
  is treated as moved. ``CFP_WHOLE_TREE=true`` scans everything.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning instead of scanning the whole tree.
- **Warn-only by default** (``CFP_FAIL`` defaults to false).
- **The search space is reported.** Every run prints how many files, lines and
  f forms it examined.

Configuration (environment variables, set by the composite action):
  CFP_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  CFP_MACROS_FILE   Path of the macros file defining the f forms.
  CFP_GLOBS         Space-separated git pathspecs.
  CFP_PATHS_IGNORE  Comma/newline-separated glob patterns to skip (``*``,
                    ``?`` and recursive ``**``).
  CFP_FAIL          "true" => exit 1 on a finding.
  CFP_WHOLE_TREE    "true" => scan every tracked matching file in full.
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

DEFAULT_GLOBS = "*.qmd *.Rmd *.md"
DEFAULT_MACROS_FILE = "latex-macros/macros.qmd"
_DEFAULT_FAIL = False

# An f-form definition: \providecommand{\XXXf}, \newcommand{\XXXf} or \def\XXXf
# (the last is how macros.qmd writes an alias such as \def\Epf{\E}).
FFORM_DEF_RE = re.compile(
    r"(?<!\\)\\(?:providecommand|newcommand)\*?\s*\{\s*\\([A-Za-z]+f)\s*\}"
    r"|(?<!\\)\\def\s*\\([A-Za-z]+f)(?![A-Za-z])"
)
# The delimiter macros that an f form replaces.
DELIMITERS = ("paren", "sb", "cb", "set", "abs", "norm", "angb")
# A macro name directly followed by a delimiter macro and its opening brace
# (the name's backslash not escaped).
PAREN_RE = re.compile(
    r"(?<!\\)\\([A-Za-z]+)\\(" + "|".join(DELIMITERS) + r")(?![A-Za-z])\{"
)
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)")
ALLOW_RE = re.compile(r"<!--\s*check-fform-paren:\s*allow\s*-->")
CODE_SPAN_RE = re.compile(r"(`+).+?\1")


class Finding(NamedTuple):
    line: int
    name: str
    delimiter: str = "paren"


def fform_names(path: str) -> Optional[Set[str]]:
    """Names of the f forms (``fitprocf``, no backslash) the file defines.

    ``None`` when the file cannot be read.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return None
    return {m.group(1) or m.group(2) for m in FFORM_DEF_RE.finditer(text)}


def paren_uses(text: str, fforms: Set[str]) -> List[Tuple[str, str]]:
    """``(foo, delimiter)`` for each ``\\foo\\paren{`` (or ``\\sb{``, ``\\cb{``)
    of ``text`` whose ``foof`` is known."""
    return [(m.group(1), m.group(2)) for m in PAREN_RE.finditer(text)
            if m.group(1) + "f" in fforms]


def _blank_closed_comments(line: str) -> str:
    """Blank each ``<!-- ... -->`` that opens and closes on this line.

    A scan with ``find`` rather than a regex: the comment-open state is
    carried across lines by the caller, so a one-line pattern is the wrong
    tool for an HTML comment, and CodeQL flags it as such.
    """
    out = line
    pos = 0
    while True:
        start = out.find("<!--", pos)
        if start < 0:
            return out
        end = out.find("-->", start + 4)
        if end < 0:
            return out
        out = out[:start] + " " * (end + 3 - start) + out[end + 3:]
        pos = end + 3


def _mask_markdown_line(line: str, in_comment: bool) -> Tuple[str, bool]:
    """Blank code spans and HTML comments; track a comment open across lines."""
    out = line
    if in_comment:
        end = out.find("-->")
        if end < 0:
            return "", True
        out, in_comment = " " * (end + 3) + out[end + 3:], False
    out = _blank_closed_comments(out)
    start = out.find("<!--")
    if start >= 0:
        out, in_comment = out[:start], True
    out = CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), out)
    return out, in_comment


def scan_file(lines: List[str], fforms: Set[str]) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)`` for a Markdown-family file."""
    found: List[Finding] = []
    examined = 0
    fence: Optional[Tuple[str, int]] = None  # (marker, length)
    in_comment = False
    in_front = bool(lines) and lines[0].strip() == "---"
    for number, raw in enumerate(lines, 1):
        examined += 1
        if in_front:
            if number > 1 and raw.strip() in ("---", "..."):
                in_front = False
            continue
        m = FENCE_RE.match(raw)
        if fence is None and m and not in_comment:
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                    and not m.group(2):
                fence = None
            continue
        masked, in_comment = _mask_markdown_line(raw, in_comment)
        allowed = ALLOW_RE.search(raw) or (
            number > 1 and ALLOW_RE.search(lines[number - 2]))
        if not allowed:
            found.extend(Finding(number, n, d)
                         for n, d in paren_uses(masked, fforms))
    return found, examined


def format_message(finding: Finding) -> str:
    name = finding.name
    return (f"\\{name}\\{finding.delimiter}{{...}} -> \\{name}f{{...}}: use the f form "
            f"\\{name}f, which takes its argument in braces.")


def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff: str) -> Tuple[Dict[str, Dict[int, str]], Set[str]]:
    """Added ``{path: {line_number: text}}`` and the set of deleted texts.

    Hunk header counts decide where a hunk ends, so an added line that begins
    with two plus signs is never mistaken for a ``+++`` file header.
    """
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
            path = None if target == "/dev/null" else target[2:] if target.startswith("b/") else target
            if path is not None:
                added.setdefault(path, {})
            continue
        m = _HUNK_RE.match(line)
        if m:
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_line = int(m.group(2))
            new_left = int(m.group(3)) if m.group(3) is not None else 1
    return added, deleted


def _glob_to_regex(pat: str) -> "re.Pattern[str]":
    """Translate a path glob to an anchored regex; supports ``**``, ``*``, ``?``."""
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


def compile_globs(patterns: List[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def _matches(rel: str, globs: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in globs)


def _split_list(value: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,\n]", value) if p.strip()]


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    skipped: bool


def _read_lines(path: str) -> Optional[List[str]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return None
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              fforms: Set[str], whole_tree: bool) -> Report:
    """Scan the added lines since ``base_ref``, or every line when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, True)
        for rel in out.splitlines():
            if rel and not _matches(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, True)
        added, deleted = parse_diff(diff)
        for rel, numbered in added.items():
            if _matches(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if not (text.strip() and text in deleted)}

    findings: List[Tuple[str, Finding]] = []
    files = lines = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        for finding in scan_file(content, fforms)[0]:
            if keep is None or finding.line in keep:
                findings.append((rel, finding))
    return Report(findings, files, lines, False)


def main() -> int:
    base_ref = os.environ.get("CFP_BASE_REF", "").strip()
    macros_file = (os.environ.get("CFP_MACROS_FILE", "").strip()
                   or DEFAULT_MACROS_FILE)
    globs = os.environ.get("CFP_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_globs(_split_list(os.environ.get("CFP_PATHS_IGNORE", "")))
    fail = _env_flag("CFP_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("CFP_WHOLE_TREE", False)

    fforms = fform_names(macros_file)
    if fforms is None:
        print(
            f"::warning::Skipping the f-form check: macros file "
            f"'{macros_file}' not found. Check out the latex-macros submodule "
            f"(submodules: true) or set 'macros-file'."
        )
        return 0

    report = run_check(base_ref, globs, ignores, fforms, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(
            f"::warning::Skipping the f-form check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every use the repository already has)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s) "
        f"against {len(fforms)} f form(s) from {macros_file} (scope: {scope})."
    )
    if not report.findings:
        print("No \\name followed by a delimiter macro "
              "where an f form exists.")
        return 0

    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{format_message(finding)}")
    print(f"\n{len(report.findings)} use(s) of a name followed by a "
          f"delimiter macro where an f form exists.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
