#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag math that spells out, by hand, what a shared macro already says.

The lab's rule (Morrison-Lab/gha#1218, prose in psw
``chapters/notation/concise-expressions.qmd``): write each chunk of math with
the semantic macro that names it, and in its most compact form.  Two cases
motivated the check: ``\E{\paren{\newoutvar - \predvalf{\newpredval}}^2}``
where ``\E{\sqf{\prederrf{\predvalf{\newpredval}}}}`` names the same prediction
error (Morrison-Lab/mlg#193), and a hand-built squared bias where
``\sqf{\biassymf{...}}`` exists (Morrison-Lab/mlg#192).

The table of expansions is read from a macros file (``CME_MACROS_FILE``,
default ``latex-macros/macros.qmd``): every single-line
``\providecommand``, ``\newcommand``, ``\renewcommand`` or ``\def`` whose body
is structured enough to recognise.  A body's ``#1``, ``#2``, ... become
wildcards, and a repeated ``#1`` must match the same text each time.  When the
file is missing the check skips with a warning.

A body is *structured enough* when it has at least ``MIN_TOKENS`` tokens
(commands, symbols and placeholders, not braces) and is not an alias of other
macros.  A lone font wrapper such as ``\mathcal{H}`` or ``\operatorname{rank}``
has two tokens and is never flagged, because the same glyphs are often a
different concept; ``\sum_{i=1}^n`` (``\sumin``) has seven and is.

What is flagged: in ``.qmd``, ``.md`` and ``.Rmd`` files, inside ``$...$`` and
``$$...$$`` math, text that matches a macro's expansion, on a line where that
macro is not already used.  When several macros match overlapping text, only
the longest match is reported.  The message names every macro with that
expansion.

What is not flagged:

- code fences and code spans, HTML comments, and YAML front matter;
- the line of a macro definition;
- a line carrying, or following, ``<!-- check-macro-expansions: allow -->``,
  the opt-out for a derivation that rewrites the chunk on purpose.

Design notes, in the model of ``check-fform-paren``:

- **Diff-scoped by default.** Only lines *added* since ``CME_BASE_REF`` are
  reported.  An added line whose exact text was also deleted in the same diff
  is treated as moved.  ``CME_WHOLE_TREE=true`` scans everything.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning instead of scanning the whole tree.
- **Warn-only by default** (``CME_FAIL`` defaults to false).
- **The search space is reported.** Every run prints how many files, lines and
  expansions it examined.

Configuration (environment variables, set by the composite action):
  CME_BASE_REF      Git ref/SHA to diff against.  Empty and not whole-tree =>
                    skip the check.
  CME_MACROS_FILE   Path of the macros file defining the expansions.
  CME_GLOBS         Space-separated git pathspecs.
  CME_PATHS_IGNORE  Comma/newline-separated glob patterns to skip (``*``,
                    ``?`` and recursive ``**``).
  CME_EXCLUDE       Comma/newline-separated macro names (no backslash) never
                    flagged.
  CME_FAIL          "true" => exit 1 on a finding.
  CME_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

_ENGINE_PATH = Path(__file__).resolve().parent.parent / "check-write-idiom" / "check-write-idiom.py"
_spec = importlib.util.spec_from_file_location("check_write_idiom_engine", _ENGINE_PATH)
assert _spec is not None and _spec.loader is not None
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd *.Rmd *.md"
DEFAULT_MACROS_FILE = "latex-macros/macros.qmd"
_DEFAULT_FAIL = False
MIN_TOKENS = 4

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)")
ALLOW_RE = re.compile(r"<!--\s*check-macro-expansions:\s*allow\s*-->")
CODE_SPAN_RE = re.compile(r"(`+).+?\1")

# A single-line macro definition; the body is the rest of the line.
DEF_RE = re.compile(
    r"^\s*\\(?:def\\(?P<n1>[A-Za-z]+)"
    r"|(?:providecommand|newcommand|renewcommand)\*?\s*\{\\(?P<n2>[A-Za-z]+)\}"
    r"(?:\[\d\])?)(?P<body>\{.*\})\s*(?:%.*)?$"
)
TOKEN_RE = re.compile(r"\\[A-Za-z]+|\\.|#\d|[A-Za-z]+|\d+|[^\sA-Za-z\d{}]")
# What an argument may be: a macro, or a letter or number with an optional
# subscript.  Anything longer is left to a human.
ARG_PATTERN = (r"(?:\\[A-Za-z]+|[A-Za-z0-9]+)"
               r"(?:_(?:[A-Za-z0-9]|\{[^{}]*\}))?")


class Expansion(NamedTuple):
    names: Tuple[str, ...]
    body: str
    regex: "re.Pattern[str]"


class Finding(NamedTuple):
    line: int
    names: Tuple[str, ...]
    text: str


def _strip_outer_braces(body: str) -> str:
    """Strip outer brace pairs that wrap the whole body."""
    body = body.strip()
    while body.startswith("{") and body.endswith("}"):
        depth = 0
        for i, ch in enumerate(body):
            depth += (ch == "{") - (ch == "}")
            if depth == 0 and i < len(body) - 1:
                return body
        body = body[1:-1].strip()
    return body


def _is_alias(tokens: List[str]) -> bool:
    return all(t.startswith("\\") and t[1:].isalpha() for t in tokens)


def _to_regex(body: str) -> "re.Pattern[str]":
    """Regex matching the body with its placeholders as wildcards."""
    seen: Set[str] = set()
    parts: List[str] = []
    for token in TOKEN_RE.findall(body):
        if re.fullmatch(r"#\d", token):
            if token in seen:
                parts.append("(?P=a" + token[1] + ")")
            else:
                seen.add(token)
                parts.append("(?P<a" + token[1] + ">" + ARG_PATTERN + ")")
        elif re.fullmatch(r"\\?[A-Za-z]+", token):
            parts.append(re.escape(token) + r"(?![A-Za-z])")
        else:
            parts.append(re.escape(token))
    return re.compile(r"(?<![A-Za-z\\])" + r"(?:\s|[{}])*".join(parts))


def load_expansions(path: str, exclude: Set[str]) -> Optional[List[Expansion]]:
    """The expansion table of a macros file, or ``None`` if unreadable."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return None
    by_body: Dict[str, List[str]] = {}
    for line in text.splitlines():
        m = DEF_RE.match(line)
        if not m:
            continue
        name = m.group("n1") or m.group("n2")
        if name in exclude:
            continue
        body = _strip_outer_braces(_strip_outer_braces(m.group("body")))
        tokens = TOKEN_RE.findall(body)
        if len(tokens) < MIN_TOKENS or _is_alias(tokens):
            continue
        key = " ".join(tokens)
        if name not in by_body.setdefault(key, []):
            by_body[key].append(name)
    return [Expansion(tuple(names), key, _to_regex(key))
            for key, names in by_body.items()]


def _math_spans(line: str, in_display: bool) -> Tuple[List[Tuple[int, int]], bool]:
    """Character spans of ``line`` that are math, and the display state after it."""
    spans: List[Tuple[int, int]] = []
    pos, start = 0, 0 if in_display else None
    n = len(line)
    while pos < n:
        ch = line[pos]
        if ch == "\\":
            pos += 2
            continue
        if ch == "$":
            double = line.startswith("$$", pos)
            if double:
                if start is not None and in_display:
                    spans.append((start, pos))
                    in_display, start = False, None
                elif start is None:
                    in_display, start = True, pos + 2
                pos += 2
                continue
            if in_display:
                pos += 1
                continue
            if start is None:
                start = pos + 1
            else:
                spans.append((start, pos))
                start = None
        pos += 1
    if start is not None:
        spans.append((start, n))  # an unclosed inline $ ends with the line
    return spans, in_display


def expansion_hits(math: str, expansions: List[Expansion]
                   ) -> List[Tuple[Tuple[str, ...], str]]:
    """``(names, matched text)`` for each longest, non-overlapping match."""
    found: List[Tuple[int, int, Tuple[str, ...]]] = []
    for exp in expansions:
        if any("\\" + n in math for n in exp.names):
            continue
        for m in exp.regex.finditer(math):
            found.append((m.start(), m.end(), exp.names))
    found.sort(key=lambda f: (-(f[1] - f[0]), f[0]))
    kept: Dict[Tuple[int, int], Tuple[str, ...]] = {}
    for start, end, names in found:
        if (start, end) in kept:
            kept[(start, end)] += tuple(n for n in names
                                        if n not in kept[(start, end)])
        elif all(end <= s or start >= e for s, e in kept):
            kept[(start, end)] = names
    return [(names, math[s:e]) for (s, e), names in sorted(kept.items())]


def _blank_closed_comments(line: str) -> str:
    """Blank each ``<!-- ... -->`` that opens and closes on this line."""
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


def scan_file(lines: List[str], expansions: List[Expansion]
              ) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)`` for a Markdown-family file."""
    found: List[Finding] = []
    examined = 0
    fence: Optional[Tuple[str, int]] = None  # (marker, length)
    in_comment = False
    in_display = False
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
        spans, in_display = _math_spans(masked, in_display)
        allowed = ALLOW_RE.search(raw) or (
            number > 1 and ALLOW_RE.search(lines[number - 2]))
        if allowed or DEF_RE.match(raw) or not spans:
            continue
        math = " ".join(masked[s:e] for s, e in spans)
        for names, text in expansion_hits(math, expansions):
            found.append(Finding(number, names, text))
    return found, examined


def format_message(finding: Finding) -> str:
    macros = " or ".join("\\" + n for n in finding.names)
    return (f"{finding.text} -> {macros}: this expression spells out what "
            f"{macros} already says; write the macro, or mark a deliberate "
            f"derivation step with <!-- check-macro-expansions: allow -->.")


def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


# The diff parser is the shared engine's: one copy, so a fix to it reaches every check.
parse_diff = engine.parse_diff


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
              expansions: List[Expansion], whole_tree: bool) -> Report:
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
        diff = _run_git([*engine.GIT_DIFF_ARGS, base.strip(), "--", *globs])
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
        for finding in scan_file(content, expansions)[0]:
            if keep is None or finding.line in keep:
                findings.append((rel, finding))
    return Report(findings, files, lines, False)


def main() -> int:
    base_ref = os.environ.get("CME_BASE_REF", "").strip()
    macros_file = (os.environ.get("CME_MACROS_FILE", "").strip()
                   or DEFAULT_MACROS_FILE)
    globs = os.environ.get("CME_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_globs(_split_list(os.environ.get("CME_PATHS_IGNORE", "")))
    exclude = {n.lstrip("\\") for n in _split_list(os.environ.get("CME_EXCLUDE", ""))}
    fail = _env_flag("CME_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("CME_WHOLE_TREE", False)

    expansions = load_expansions(macros_file, exclude)
    if expansions is None:
        print(
            f"::warning::Skipping the macro-expansion check: macros file "
            f"'{macros_file}' not found. Check out the latex-macros submodule "
            f"(submodules: true) or set 'macros-file'."
        )
        return 0

    report = run_check(base_ref, globs, ignores, expansions, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        # With no base-ref (a push run) the skip is expected, so it is not an annotation.
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the macro-expansion check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every use the repository already has)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s) "
        f"against {len(expansions)} expansion(s) from {macros_file} (scope: {scope})."
    )
    if not report.findings:
        print("No math spells out a shared macro's expansion.")
        return 0

    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{format_message(finding)}")
    print(f"\n{len(report.findings)} expression(s) spell out a shared "
          f"macro's expansion.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
