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
ALLOW_RE = re.compile(r"<!--\s*check-local-macros:\s*allow\s*-->")


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
        m = mdmask.FENCE_RE.match(raw)
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
        masked, in_comment_next = mdmask.mask_markdown_line(raw, in_comment)
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


# The git, glob and file helpers come from check-common (gha#1856).
compile_globs = diffscope.compile_ignores


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    definitions: int
    unchecked_overrides: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              overrides: List["re.Pattern[str]"], library: Optional[Set[str]],
              whole_tree: bool) -> Report:
    """Scan the added lines since ``base_ref``, or every line when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        paths = diffscope.git_paths(["ls-files", "--", *globs])
        if paths is None:
            return Report([], 0, 0, 0, 0, True)
        for rel in paths:
            if not diffscope.ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, 0, True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, 0, True)
        diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                                 base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, 0, 0, True)
        added, deleted = diffscope.parse_diff(diff)
        for rel, numbered in added.items():
            if diffscope.ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if not (text.strip() and text in deleted)}

    findings: List[Tuple[str, Finding]] = []
    files = lines = defs = unchecked = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        is_override = diffscope.ignored(rel, overrides)
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
    ignores = compile_globs(diffscope.split_list(os.environ.get("LMD_PATHS_IGNORE", "")))
    overrides = compile_globs(diffscope.split_list(
        os.environ.get("LMD_OVERRIDE_FILES", "") or DEFAULT_OVERRIDES))
    library_paths = os.environ.get("LMD_LIBRARY", "").split()
    library = library_names(library_paths) if library_paths else None
    fail = diffscope.env_flag("LMD_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("LMD_WHOLE_TREE", False)

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
