#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag LaTeX macros defined outside ``Morrison-Lab/macros``.

The lab's rule (Morrison-Lab/gha#1077, check 2): new macros go only in
``Morrison-Lab/macros``, never in an applied repository, unless a repository
explicitly overrides one specific macro that the library already has.

What is flagged: ``\newcommand``, ``\renewcommand``, ``\providecommand``,
``\DeclareMathOperator``, ``\DeclarePairedDelimiter``, ``\DeclareRobustCommand``,
``\NewDocumentCommand`` and its relatives, ``\def``, ``\gdef``, ``\edef`` and
``\xdef`` in ``.qmd``, ``.Rmd``, ``.md``, ``.tex``, ``.sty``, ``.cls`` and
``.html`` files (header files that load macros into MathJax).

What is not flagged:

- code fences and code spans in Markdown-family files, except fences whose
  language is ``tex``, ``latex`` or a raw ``{=tex}``/``{=latex}``/``{=html}``
  block, which is where a Quarto page keeps definitions;
- HTML comments in Markdown-family files, and YAML front matter;
- ``%`` comments in ``.tex``, ``.sty`` and ``.cls`` files;
- a line carrying, or following, ``<!-- check-local-macros: allow -->``;
- an *override file* (default ``macros-override.*``): its definitions are
  allowed only when the library already defines the same name. An override
  that defines a name the library lacks is flagged. The library's names are
  read from the files in ``LMD_LIBRARY`` (for example the ``latex-macros``
  submodule's ``macros.qmd``); with no library given the override files'
  names cannot be checked, which the run reports.

Design notes, in the model of ``check-literal-math-letters``:

- **Diff-scoped by default.** Only lines *added* since ``LMD_BASE_REF`` are
  reported, so a repository's existing local macros are not reflagged on every
  unrelated edit. An added line whose exact text was also deleted in the same
  diff is treated as moved. ``LMD_WHOLE_TREE=true`` scans everything.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning instead of scanning the whole tree.
- **Warn-only by default** (``LMD_FAIL`` defaults to false).
- **The search space is reported.** Every run prints how many files, lines and
  definitions it examined.

Configuration (environment variables, set by the composite action):
  LMD_BASE_REF       Git ref/SHA to diff against. Empty and not whole-tree =>
                     skip the check.
  LMD_GLOBS          Space-separated git pathspecs.
  LMD_PATHS_IGNORE   Comma/newline-separated glob patterns to skip (``*``,
                     ``?`` and recursive ``**``).
  LMD_OVERRIDE_FILES Comma/newline-separated glob patterns naming override
                     files (default ``**/macros-override.*``).
  LMD_LIBRARY        Space-separated paths of library files whose definitions
                     define the allowed override names.
  LMD_FAIL           "true" => exit 1 on a finding.
  LMD_WHOLE_TREE     "true" => scan every tracked matching file in full.
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

DEFAULT_GLOBS = "*.qmd *.Rmd *.md *.tex *.sty *.cls *.html"
DEFAULT_OVERRIDES = "**/macros-override.*,macros-override.*"
_DEFAULT_FAIL = False

TEX_SUFFIXES = (".tex", ".sty", ".cls")
TEX_FENCE_LANGS = frozenset({"tex", "latex", "{=tex}", "{=latex}", "{=html}"})

# A definition command, then an optional brace, then the \name being defined.
DEFINITION_RE = re.compile(
    r"(?<!\\)\\(?:newcommand|renewcommand|providecommand|DeclareMathOperator"
    r"|DeclarePairedDelimiter|DeclareRobustCommand|NewDocumentCommand"
    r"|RenewDocumentCommand|ProvideDocumentCommand|DeclareDocumentCommand"
    r"|def|gdef|edef|xdef)(?![A-Za-z])\*?\s*\{?\s*(\\[A-Za-z@]+)?"
)
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)")
ALLOW_RE = re.compile(r"<!--\s*check-local-macros:\s*allow\s*-->")
CODE_SPAN_RE = re.compile(r"(`+).+?\1")


class Finding(NamedTuple):
    line: int
    name: str
    kind: str  # "local" or "override"


def definitions(text: str) -> List[str]:
    """Names (``\\foo``, or empty when unparsed) defined by one line of text."""
    return [m.group(1) or "" for m in DEFINITION_RE.finditer(text)]


def library_names(paths: List[str]) -> Set[str]:
    """Macro names the library defines, read from raw text (no fence logic)."""
    names: Set[str] = set()
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    names.update(n for n in definitions(line) if n)
        except OSError:
            continue
    return names


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


def scan_file(rel: str, lines: List[str]) -> Tuple[List[Tuple[int, str]], int]:
    """``([(line, name), ...], lines examined)`` for every definition found."""
    found: List[Tuple[int, str]] = []
    examined = 0
    if rel.endswith(TEX_SUFFIXES):
        for number, raw in enumerate(lines, 1):
            text = re.sub(r"(?<!\\)%.*", "", raw)
            allowed = ALLOW_RE.search(raw) or (
                number > 1 and ALLOW_RE.search(lines[number - 2]))
            examined += 1
            if allowed:
                continue
            found.extend((number, n) for n in definitions(text))
        return found, examined

    fence: Optional[Tuple[str, int, bool]] = None  # (marker, length, scan?)
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
            lang = m.group(2).lower()
            fence = (m.group(1)[0], len(m.group(1)), lang in TEX_FENCE_LANGS)
            continue
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                    and not m.group(2):
                fence = None
                continue
            if fence[2]:
                allowed = ALLOW_RE.search(raw) or (
                    number > 1 and ALLOW_RE.search(lines[number - 2]))
                if not allowed:
                    found.extend((number, n) for n in definitions(raw))
            continue
        masked, in_comment_next = _mask_markdown_line(raw, in_comment)
        in_comment = in_comment_next
        allowed = ALLOW_RE.search(raw) or (
            number > 1 and ALLOW_RE.search(lines[number - 2]))
        if not allowed:
            found.extend((number, n) for n in definitions(masked))
    return found, examined


def format_message(finding: Finding) -> str:
    name = finding.name or "a macro"
    if finding.kind == "override":
        return (f"override defines {name}, which Morrison-Lab/macros does not "
                f"define. An override file may redefine only a macro the "
                f"library already has; add a new macro to Morrison-Lab/macros "
                f"instead.")
    return (f"{name} is defined outside Morrison-Lab/macros. Add a new macro "
            f"to that repository and use it from here; to override one "
            f"library macro for this repository, define it in a "
            f"macros-override file.")


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
    definitions: int
    unchecked_overrides: int
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
              overrides: List["re.Pattern[str]"], library: Optional[Set[str]],
              whole_tree: bool) -> Report:
    """Scan the added lines since ``base_ref``, or every line when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, 0, 0, True)
        for rel in out.splitlines():
            if rel and not _matches(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, 0, True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, 0, 0, True)
        added, deleted = parse_diff(diff)
        for rel, numbered in added.items():
            if _matches(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if not (text.strip() and text in deleted)}

    findings: List[Tuple[str, Finding]] = []
    files = lines = defs = unchecked = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        is_override = _matches(rel, overrides)
        for number, name in scan_file(rel, content)[0]:
            if keep is not None and number not in keep:
                continue
            defs += 1
            if is_override:
                if library is None:
                    unchecked += 1
                elif name not in library:
                    findings.append((rel, Finding(number, name, "override")))
            else:
                findings.append((rel, Finding(number, name, "local")))
    return Report(findings, files, lines, defs, unchecked, False)


def main() -> int:
    base_ref = os.environ.get("LMD_BASE_REF", "").strip()
    globs = os.environ.get("LMD_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_globs(_split_list(os.environ.get("LMD_PATHS_IGNORE", "")))
    overrides = compile_globs(_split_list(
        os.environ.get("LMD_OVERRIDE_FILES", "") or DEFAULT_OVERRIDES))
    library_paths = os.environ.get("LMD_LIBRARY", "").split()
    library = library_names(library_paths) if library_paths else None
    fail = _env_flag("LMD_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("LMD_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, overrides, library, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        # With no base-ref (a push run) the skip is expected, so it is not an annotation.
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the local-macros check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every macro the repository already defines)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s), "
        f"{report.definitions} definition(s) (scope: {scope})."
    )
    if report.unchecked_overrides:
        print(
            f"::warning::{report.unchecked_overrides} definition(s) in override "
            f"files were not checked against the library: pass 'library' (for "
            f"example the latex-macros submodule's macros.qmd) to check them."
        )
    if not report.findings:
        print("No macros defined outside Morrison-Lab/macros.")
        return 0

    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{format_message(finding)}")
    print(f"\n{len(report.findings)} definition(s) outside Morrison-Lab/macros.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
