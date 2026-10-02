#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""
Diff-scoped prose check for Quarto and Markdown sources.

Two rules, each reported as a GitHub ``::error file=,line=::`` annotation:

``notes-div-content``
    A ``::: notes`` (or ``::: {.notes}``) div whose body holds a
    theorem-like example or remark. Decidable test: the body contains a
    nested div whose id starts with ``exm-``, ``rem-``, ``def-``, ``thm-``
    or ``exr-``, or its first non-blank line starts with "Example",
    "Remark" or "Note:" (case-insensitive, optional bold or italic marks).
    Fix: use an ``#exm-``, ``#rem-`` or ``#def-`` div.

``banned-idiom``
    A case-insensitive whole-phrase match against a list of idioms,
    cliches and slang (``banned-idioms.txt`` next to this script, or the
    ``idioms-file`` input). The house style is plain, literal prose. See
    https://github.com/Morrison-Lab/psw.

What is never scanned for ``banned-idiom``: fenced code blocks, inline code,
math, HTML comments, link destinations and URLs, attribute braces such as
``{#sec-deep-dive}``, shortcodes, citation and cross-reference keys, and
YAML front matter keys other than ``title``, ``subtitle`` and
``description``.

Design notes:
- **Diff-scoped by default**, with the same base-ref model as check-typos:
  only findings on lines a diff adds are reported, so a corpus's existing
  prose is not reflagged on every unrelated edit. With no base-ref, or a
  base-ref this clone cannot see, the check is *skipped* with a warning.
  There is no whole-tree fallback. Pass ``CQP_BASE_REF=all`` to scan every
  tracked file.
- **Blocking by default.** Only an explicit ``false`` opts out of failing.
- A phrase list cannot see context. Exempt a line with
  ``<!-- prose-allow: phrase -->`` (on the same line, or alone on the line
  before), or list ``glob: phrase`` in the allow-file.

Configuration (environment variables, set by the composite action):
  CQP_TARGET        Repository root to check (default: GITHUB_WORKSPACE or cwd).
  CQP_GLOBS         Space-separated git pathspecs (default ``*.qmd *.md``).
  CQP_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  CQP_BASE_REF      Git ref/SHA to diff against, or ``all``. Empty => skip.
  CQP_IDIOMS_FILE   Phrase list replacing the bundled one.
  CQP_ALLOW_FILE    Optional ``glob: phrase`` exemptions, one per line.
  CQP_FAIL          "false" => non-blocking; default "true" => blocking.
"""

from __future__ import annotations

import bisect
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

_DEFAULT_FAIL = True
_DEFAULT_GLOBS = "*.qmd *.md"
_DEFAULT_IDIOMS = Path(__file__).resolve().parent / "banned-idioms.txt"
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_GIT = (
    "git",
    "-c",
    "core.quotepath=false",
    "-c",
    "diff.noprefix=false",
    "-c",
    "diff.renames=true",
)

RULE_NOTES = "notes-div-content"
RULE_IDIOM = "banned-idiom"
_NOTES_FIX = "Use an #exm-, #rem- or #def- div, not a notes div."
_PSW_URL = "https://github.com/Morrison-Lab/psw"

# Stands in for every character that must not be scanned. It is neither a
# word character nor whitespace, so no phrase can match through it.
_MASK = "\x01"

_FRONT_MATTER_KEYS = {"title", "subtitle", "description"}
_THEOREM_ID_RE = re.compile(r"#((?:exm|rem|def|thm|exr)-[^\s}]*)")
_NOTES_CLASS_RE = re.compile(r"^notes$|(?:^|[\s{])\.notes(?=[\s}]|$)")
_FIRST_LINE_RE = re.compile(
    r"^\s*(?:(?:\*\*|__|\*|_)\s*)?(?:(?:example|remark)s?\b"
    r"|note\s*(?:\*\*|__|\*|_)?\s*:)",
    re.IGNORECASE,
)
_DIV_FENCE_RE = re.compile(r"^\s*(:{3,})\s*(.*?)\s*$")
_CODE_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_ALLOW_RE = re.compile(r"<!--\s*prose-allow:\s*(.*?)\s*-->", re.IGNORECASE | re.DOTALL)
_COMMENT_ONLY_RE = re.compile(r"^\s*<!--.*-->\s*$", re.DOTALL)
_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:(.*)$")

# Inline constructs whose text is not prose. Order matters little: each
# match is replaced by mask characters of the same length.
_INLINE_MASKS = [
    re.compile(r"\{\{<.*?>\}\}"),
    re.compile(r"</?[A-Za-z][^>\n]*>"),
    re.compile(r"https?://[^\s<>\"]+"),
    re.compile(r"\]\([^)\n]*\)"),
    re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s*\S+"),
    re.compile(r"\{\s*[#.][^{}\n]*\}"),
    re.compile(r"\{[^{}\n]*\b\w+=[^{}\n]*\}"),
    re.compile(r"@\w[\w:\-./]*"),
    re.compile(r"(?<![\\$\w])\$(?=\S)(?!\$)[^$\n]*?(?<=\S)(?<!\\)\$(?!\d)"),
]
_DISPLAY_MATH_PAIR_RE = re.compile(r"\$\$.*?\$\$")


class Finding(NamedTuple):
    """One finding. ``end_line`` differs from ``line`` for a wrapped phrase."""

    path: str
    line: int
    end_line: int
    rule: str
    message: str


class Idiom(NamedTuple):
    """A phrase as written in the list, with its compiled whole-phrase regex."""

    text: str
    norm: str
    regex: "re.Pattern[str]"


class Allow(NamedTuple):
    """An allow-file entry: a path glob (None means every path) and a phrase."""

    path_re: Optional["re.Pattern[str]"]
    norm: str


class _Div(NamedTuple):
    colons: int
    is_notes: bool
    start: int


# ---------------------------------------------------------------- git helpers


def _run_git(args: List[str], cwd: Optional[str] = None) -> Optional[str]:
    try:
        proc = subprocess.run(
            [*_GIT, *args],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _run_git_checked(args: List[str], cwd: Optional[str] = None) -> str:
    """Return stdout, or raise RuntimeError with git's stderr."""
    try:
        proc = subprocess.run(
            [*_GIT, *args],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is not available") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or (
            f"git {' '.join(args)} exited {proc.returncode}"
        )
        raise RuntimeError(detail)
    return proc.stdout


def _ref_exists(ref: str, cwd: str) -> bool:
    return _run_git(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=cwd) is not None


def _normalize_path(path: str) -> str:
    # Strip a `./` prefix only; lstrip("./") would eat the dot of `.github/`.
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _diff_new_file_path(raw: str) -> Optional[str]:
    """Path from a unified-diff ``+++ `` header, or None for ``/dev/null``.

    Call only outside a hunk: an added line whose text starts with ``++ ``
    also renders as ``+++ ...`` and is told apart from a header by position.
    """
    target = raw[4:].split("\t", 1)[0]
    if len(target) >= 2 and target.startswith('"') and target.endswith('"'):
        target = target[1:-1]
    if target == "/dev/null":
        return None
    if target.startswith(("a/", "b/")):
        target = target[2:]
    return _normalize_path(target)


def _added_line_numbers(
    base_ref: str, pathspecs: List[str], cwd: Optional[str] = None
) -> Dict[str, Set[int]]:
    """{file: {new-file line numbers added}} vs the merge base of base_ref and HEAD."""
    diff = _run_git_checked(
        ["diff", "--unified=0", "--no-color", f"{base_ref}...HEAD", "--", *pathspecs],
        cwd=cwd,
    )
    result: Dict[str, Set[int]] = {}
    cur_path: Optional[str] = None
    new_lineno = 0
    in_hunk = False
    for raw in diff.splitlines():
        if raw.startswith("diff ") or raw.startswith("--- "):
            in_hunk = False
            continue
        if raw.startswith("+++ ") and not in_hunk:
            cur_path = _diff_new_file_path(raw)
            if cur_path is not None:
                result.setdefault(cur_path, set())
            continue
        if raw.startswith("@@"):
            in_hunk = True
            m = _HUNK_RE.match(raw)
            new_lineno = int(m.group(1)) if m else 0
            continue
        if raw.startswith("+"):
            if cur_path is not None:
                result[cur_path].add(new_lineno)
            new_lineno += 1
    return result


def _tracked_files(pathspecs: List[str], cwd: Optional[str] = None) -> List[str]:
    out = _run_git_checked(["ls-files", "-z", "--", *pathspecs], cwd=cwd)
    return [_normalize_path(p) for p in out.split("\0") if p]


# ------------------------------------------------------------- path globbing


def _glob_to_regex(pat: str) -> "re.Pattern[str]":
    """Translate a path glob to an anchored regex; supports ``**``, ``*``, ``?``."""
    i, n, out = 0, len(pat), []
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i : i + 2] == "**":
                i += 2
                if pat[i : i + 1] == "/":
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


def _compile_ignores(patterns: List[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def _ignored(rel: str, ignores: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in ignores)


def _split_list(value: str) -> List[str]:
    return [tok.strip() for tok in re.split(r"[,\n]", value or "") if tok.strip()]


# ------------------------------------------------------------ phrase handling


def _norm(text: str) -> str:
    """Lowercase, straighten quotes, and make space and hyphen the same."""
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"[\s-]+", " ", text.replace("*", "").lower()).strip()


# Between the words of a phrase: spaces, a hyphen joining two word
# characters, or one line break (never a blank line, so a phrase cannot span
# two paragraphs).
_SEP = r"(?:[ \t]+|(?<=\w)-(?=\w)|[ \t]*\n(?![ \t]*\n)[ \t]*)+"


def _phrase_regex(phrase: str) -> "re.Pattern[str]":
    parts = [p for p in re.split(r"[\s-]+", phrase.strip()) if p]
    pieces = []
    for part in parts:
        wild = part.endswith("*")
        stem = part.rstrip("*")
        if not stem:
            raise ValueError(f"phrase {phrase!r} has a word that is only '*'")
        pieces.append(re.escape(stem) + (r"\w*" if wild else ""))
    return re.compile(r"(?<!\w)" + _SEP.join(pieces) + r"(?!\w)", re.IGNORECASE)


def load_idioms(path: Path) -> List[Idiom]:
    """Parse a phrase list. An empty list is an error: it would check nothing."""
    idioms: List[Idiom] = []
    seen: Set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        norm = _norm(line)
        if norm in seen:
            continue
        seen.add(norm)
        try:
            regex = _phrase_regex(line)
        except ValueError as exc:
            raise ValueError(f"{path}: {exc}") from exc
        idioms.append(Idiom(text=line, norm=norm, regex=regex))
    if not idioms:
        raise ValueError(
            f"{path} lists no phrases; a check with an empty list would "
            "examine nothing and pass."
        )
    return idioms


def load_allow(path: Path) -> List[Allow]:
    """Parse ``glob: phrase`` lines; a line with no glob allows the phrase everywhere."""
    entries: List[Allow] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\S+):\s+(.+)$", line)
        if m:
            entries.append(Allow(_glob_to_regex(m.group(1)), _norm(m.group(2))))
        else:
            entries.append(Allow(None, _norm(line)))
    return entries


# ---------------------------------------------------------------- the scanner


def _mask_span(match: "re.Match[str]") -> str:
    return _MASK * len(match.group(0))


def _mask_inline(line: str) -> str:
    for pattern in _INLINE_MASKS:
        line = pattern.sub(_mask_span, line)
    return line


def _split_comment(line: str, in_comment: bool) -> Tuple[str, bool, Set[str]]:
    """Mask HTML comments in ``line``; return (line, still-in-comment, allowed).

    Code spans are masked first so a ``<!--`` quoted in backticks cannot open
    a comment, except at the start of a line already inside one, where the
    first ``-->`` closes it whatever precedes it.
    """
    out: List[str] = []
    if in_comment:
        end = line.find("-->")
        if end < 0:
            return _MASK * len(line), True, set()
        out.append(_MASK * (end + 3))
        line = line[end + 3 :]
        in_comment = False
    line = _CODE_SPAN_RE.sub(_mask_span, line)
    allowed: Set[str] = set()
    for m in _ALLOW_RE.finditer(line):
        for phrase in m.group(1).split(","):
            if phrase.strip():
                allowed.add(_norm(phrase))
    pos = 0
    while True:
        start = line.find("<!--", pos)
        if start < 0:
            out.append(line[pos:])
            break
        out.append(line[pos:start])
        end = line.find("-->", start + 4)
        if end < 0:
            out.append(_MASK * (len(line) - start))
            in_comment = True
            break
        out.append(_MASK * (end + 3 - start))
        pos = end + 3
    return "".join(out), in_comment, allowed


def _is_blank(text: str) -> bool:
    return not text.replace(_MASK, " ").strip()


class _Scan:
    """Single pass over one file's lines.

    Produces the text the idiom rule may read (``masked``), the
    ``prose-allow`` exemptions by line number, and the notes-div findings.
    """

    def __init__(self, path: str, lines: List[str]):
        self.path = path
        self.lines = lines
        self.masked: List[str] = []
        self.allow: Dict[int, Set[str]] = {}
        self.findings: List[Finding] = []
        self._stack: List[_Div] = []
        self._pending: Set[int] = set()  # notes divs awaiting their first line

    def run(self) -> "_Scan":
        first_body = self._front_matter()
        fence: Optional[Tuple[str, int]] = None
        in_comment = False
        in_math = False
        for idx in range(first_body, len(self.lines)):
            lineno = idx + 1
            raw = self.lines[idx]
            if fence is not None:
                fence = self._in_fence(raw, fence)
                self.masked.append(_MASK * len(raw))
                continue
            if in_math:
                in_math = "$$" not in raw
                self.masked.append(_MASK * len(raw))
                continue
            if not in_comment:
                opened = _CODE_FENCE_RE.match(raw)
                if opened and not (
                    opened.group(1)[0] == "`" and "`" in opened.group(2)
                ):
                    self._consume_first_line("```", lineno)
                    fence = (opened.group(1)[0], len(opened.group(1)))
                    self.masked.append(_MASK * len(raw))
                    continue
            text, in_comment, allowed = _split_comment(raw, in_comment)
            if allowed:
                self.allow.setdefault(lineno, set()).update(allowed)
                if _COMMENT_ONLY_RE.match(raw):
                    self.allow.setdefault(lineno + 1, set()).update(allowed)
            if _is_blank(text):
                self.masked.append(text)
                continue
            fence_m = _DIV_FENCE_RE.match(text)
            if fence_m:
                self._div_fence(fence_m, lineno)
                self.masked.append(_MASK * len(raw))
                continue
            text = _DISPLAY_MATH_PAIR_RE.sub(_mask_span, text)
            if "$$" in text:
                cut = text.index("$$")
                text = text[:cut] + _MASK * (len(text) - cut)
                in_math = True
            self._consume_first_line(text, lineno)
            self.masked.append(_mask_inline(text))
        return self

    # -- front matter

    def _front_matter(self) -> int:
        """Handle a leading YAML block; return the index of the first body line."""
        if not self.lines or self.lines[0].rstrip() != "---":
            return 0
        self.masked.append(_MASK * len(self.lines[0]))
        active = False
        for idx in range(1, len(self.lines)):
            raw = self.lines[idx]
            if raw.rstrip() in ("---", "..."):
                self.masked.append(_MASK * len(raw))
                return idx + 1
            key = _KEY_RE.match(raw)
            if key:
                active = key.group(1).lower() in _FRONT_MATTER_KEYS
                if active:
                    cut = key.start(2)
                    self.masked.append(_MASK * cut + _mask_inline(raw[cut:]))
                    continue
            elif raw[:1] not in (" ", "\t", ""):
                active = False
            if active and raw.strip():
                self.masked.append(_mask_inline(raw))
            else:
                self.masked.append(_MASK * len(raw))
        # No closing marker: not front matter after all. Rescan as body.
        self.masked.clear()
        return 0

    # -- code fences

    @staticmethod
    def _in_fence(raw: str, fence: Tuple[str, int]) -> Optional[Tuple[str, int]]:
        """Return the fence still open after ``raw``, or None once it closes."""
        char, length = fence
        m = re.match(r"^\s*(`{3,}|~{3,})\s*$", raw)
        if m and m.group(1)[0] == char and len(m.group(1)) >= length:
            return None
        return fence

    # -- notes divs

    def _consume_first_line(self, text: str, lineno: int) -> None:
        """Test the first non-blank line of each notes div still waiting for one."""
        if not self._pending or _is_blank(text):
            return
        hit = _FIRST_LINE_RE.match(text.replace(_MASK, " "))
        if hit:
            self.findings.append(
                Finding(
                    self.path,
                    lineno,
                    lineno,
                    RULE_NOTES,
                    "notes-div-content: a notes div opens with an example or "
                    f"remark. {_NOTES_FIX}",
                )
            )
        self._pending.clear()

    def _div_fence(self, match: "re.Match[str]", lineno: int) -> None:
        colons = len(match.group(1))
        info = re.sub(r"\s*:+$", "", match.group(2)).strip()
        if info:
            self._open_div(colons, info, lineno)
        else:
            self._close_div(colons)

    def _open_div(self, colons: int, info: str, lineno: int) -> None:
        in_notes = any(d.is_notes for d in self._stack)
        theorem = _THEOREM_ID_RE.search(info)
        if in_notes and theorem:
            self.findings.append(
                Finding(
                    self.path,
                    lineno,
                    lineno,
                    RULE_NOTES,
                    f"notes-div-content: a notes div holds a #{theorem.group(1)} "
                    f"div. {_NOTES_FIX}",
                )
            )
        self._pending.clear()  # this fence is the first line of any open notes div
        is_notes = bool(_NOTES_CLASS_RE.search(info))
        self._stack.append(_Div(colons, is_notes, lineno))
        if is_notes:
            self._pending.add(lineno)

    def _close_div(self, colons: int) -> None:
        """Close the nearest open div with the same colon count, else the innermost.

        Any div opened inside the one being closed and never closed itself is
        closed with it, so a longer outer fence ends an unclosed inner one.
        """
        for depth in range(len(self._stack) - 1, -1, -1):
            if self._stack[depth].colons == colons:
                del self._stack[depth:]
                return
        if self._stack:
            self._stack.pop()


def _find_idioms(
    path: str,
    scan: _Scan,
    idioms: List[Idiom],
    allow: List[Allow],
) -> List[Finding]:
    text = "\n".join(scan.masked).replace("\u2019", "'").replace("\u2018", "'")
    starts = [0]
    for line in scan.masked:
        starts.append(starts[-1] + len(line) + 1)

    def line_of(offset: int) -> int:
        return bisect.bisect_right(starts, offset)

    hits = []
    for idiom in idioms:
        for m in idiom.regex.finditer(text):
            hits.append((m.start(), -(m.end() - m.start()), m.end(), idiom, m.group(0)))
    hits.sort(key=lambda h: (h[0], h[1]))

    findings: List[Finding] = []
    covered_until = -1
    for start, _neg_len, end, idiom, matched in hits:
        if start < covered_until:
            continue  # overlaps a longer or earlier match: report once
        first, last = line_of(start), line_of(end - 1)
        names = {idiom.norm, _norm(matched)}
        if any(names & scan.allow.get(n, set()) for n in range(first, last + 1)):
            covered_until = end
            continue
        if any(
            (a.path_re is None or a.path_re.match(path)) and a.norm in names
            for a in allow
        ):
            covered_until = end
            continue
        covered_until = end
        shown = re.sub(r"\s+", " ", matched)
        findings.append(
            Finding(
                path,
                first,
                last,
                RULE_IDIOM,
                f'banned-idiom: "{shown}" is an idiom, cliche or slang. Say it '
                "in plain, literal words, or add "
                f"<!-- prose-allow: {idiom.text.replace('*', '')} --> if it is a quotation.",
            )
        )
    return findings


def scan_text(
    path: str, text: str, idioms: List[Idiom], allow: List[Allow]
) -> List[Finding]:
    """All findings in one file's text, before diff scoping."""
    scan = _Scan(path, text.splitlines()).run()
    findings = scan.findings + _find_idioms(path, scan, idioms, allow)
    return sorted(findings, key=lambda f: (f.line, f.rule))


# ----------------------------------------------------------------- the driver


def _env_fail() -> bool:
    """Fail-closed: only an explicit 'false' (trimmed, case-insensitive) opts out."""
    raw = os.environ.get("CQP_FAIL")
    if raw is None:
        return _DEFAULT_FAIL
    return "".join(raw.split()).lower() != "false"


def collect_findings(
    *,
    base_ref: str,
    globs: List[str],
    ignores: List["re.Pattern[str]"],
    idioms: List[Idiom],
    allow: List[Allow],
    cwd: str,
) -> Tuple[List[Finding], bool, int, int]:
    """Return (in-scope findings, skipped, dropped-count, files-scanned).

    ``skipped`` is True when there is no diff to check against: base_ref was
    never given, or is not a commit this clone can see. There is no
    whole-tree fallback. A base_ref that exists but whose diff fails is a
    tool error.
    """
    if not base_ref:
        return [], True, 0, 0
    whole_tree = base_ref == "all"
    pathspecs = globs or ["."]
    added: Dict[str, Set[int]] = {}
    if whole_tree:
        candidates = _tracked_files(pathspecs, cwd=cwd)
    else:
        if not _ref_exists(base_ref, cwd):
            return [], True, 0, 0
        added = _added_line_numbers(base_ref, pathspecs, cwd=cwd)
        candidates = sorted(added)
    files = [
        p for p in candidates if not _ignored(p, ignores) and (Path(cwd) / p).is_file()
    ]
    in_scope: List[Finding] = []
    dropped = 0
    for rel in files:
        text = (Path(cwd) / rel).read_text(encoding="utf-8", errors="replace")
        for finding in scan_text(rel, text, idioms, allow):
            lines = range(finding.line, finding.end_line + 1)
            if whole_tree or any(n in added.get(rel, set()) for n in lines):
                in_scope.append(finding)
            else:
                dropped += 1
    return in_scope, False, dropped, len(files)


def _escape_property(value: str) -> str:
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def _escape_message(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _write_summary(findings: List[Finding], whole_tree: bool, base_ref: str) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    scope = "whole tracked tree" if whole_tree else f"lines added since {base_ref[:12]}"
    lines = [
        "### check-quarto-prose",
        "",
        f"{len(findings)} finding(s) in the {scope}.",
        "",
        "| File | Line | Rule | Message |",
        "| --- | --- | --- | --- |",
    ]
    for f in findings:
        message = f.message.replace("|", "\\|")
        lines.append(f"| `{f.path}` | {f.line} | `{f.rule}` | {message} |")
    lines.extend(["", f"Prose rules: {_PSW_URL}", ""])
    with open(summary, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def _resolve_file(cwd: str, value: str, what: str) -> Optional[Path]:
    """Resolve an optional input file under ``cwd``; a named-but-missing one is an error."""
    if not value:
        return None
    path = Path(cwd) / value
    if not path.is_file():
        raise FileNotFoundError(f"{what} {value!r} does not exist under the repository root.")
    return path


def main() -> int:
    target = os.environ.get("CQP_TARGET") or os.environ.get("GITHUB_WORKSPACE") or "."
    if not Path(target).exists():
        print(f"::error::check-quarto-prose: path {target!r} does not exist.")
        return 1
    cwd = str(Path(target).resolve())
    inside = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=cwd)
    if inside is None or inside.strip() != "true":
        print(f"::error::check-quarto-prose: {target!r} is not a git repository.")
        return 1

    try:
        idioms_path = _resolve_file(
            cwd, os.environ.get("CQP_IDIOMS_FILE", "").strip(), "idioms-file"
        )
        allow_path = _resolve_file(
            cwd, os.environ.get("CQP_ALLOW_FILE", "").strip(), "allow-file"
        )
        idioms = load_idioms(idioms_path or _DEFAULT_IDIOMS)
        allow = load_allow(allow_path) if allow_path else []
    except (OSError, ValueError) as exc:
        print(f"::error::check-quarto-prose: {exc}")
        return 1

    globs = os.environ.get("CQP_GLOBS", _DEFAULT_GLOBS).split()
    ignores = _compile_ignores(_split_list(os.environ.get("CQP_PATHS_IGNORE", "")))
    base_ref = os.environ.get("CQP_BASE_REF", "").strip()
    fail = _env_fail()

    try:
        findings, skipped, dropped, scanned = collect_findings(
            base_ref=base_ref,
            globs=globs,
            ignores=ignores,
            idioms=idioms,
            allow=allow,
            cwd=cwd,
        )
    except RuntimeError as exc:
        print(f"::error::check-quarto-prose: {exc}")
        return 1

    if skipped:
        reason = (
            f"base-ref '{base_ref}' is not a commit this clone can see"
            if base_ref
            else "no base-ref given"
        )
        print(
            "::warning::Skipping the prose check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            "reflag prose the corpus already carries)."
        )
        return 0

    whole_tree = base_ref == "all"
    scope = "whole tracked tree" if whole_tree else f"lines added since {base_ref[:12]}"
    print(f"Checking prose ({scope}): {scanned} file(s), {len(idioms)} idiom(s).\n")
    if dropped:
        print(
            f"{dropped} finding(s) sit outside this diff's added lines; "
            "ignored (existing prose)."
        )
    if not findings:
        print("No prose findings.")
        return 0

    level = "error" if fail else "warning"
    for f in findings:
        loc = f"file={_escape_property(f.path)},line={f.line}"
        if f.end_line != f.line:
            loc += f",endLine={f.end_line}"
        print(f"::{level} {loc}::{_escape_message(f.message)}")
    _write_summary(findings, whole_tree, base_ref)
    print(f"\n{len(findings)} prose finding(s). Prose rules: {_PSW_URL}")
    if fail:
        print(f"::error::check-quarto-prose: {len(findings)} finding(s).")
        return 1
    print(
        f"::warning::check-quarto-prose: {len(findings)} finding(s) "
        "(fail: false, so not blocking)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
