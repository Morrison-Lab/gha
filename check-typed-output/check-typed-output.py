#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""
Flag typed ("faked") code output in Quarto (``.qmd``) sources.

The rule this enforces: never type, paste or fake output. Code whose output a
page shows runs as an executable ``{r}``/``{python}`` chunk, so the page shows
what the code actually prints. Two shapes stand in for that instead, and both
are flagged:

- **An output comment** inside a code fence -- a plain ``python``/``r``/
  ``julia`` fence, or an executable ``{r}``/``{python}``/``{julia}`` chunk --
  whose comment stands in for a printed value: ``# ->``, ``#->``, ``# =>``,
  ``#>`` (the output prefix reprex prints, and knitr prints when set up
  with ``comment = "#>"``), ``# Output:``/``# output:``. knitr's default
  prefix ``##`` is left out, since R code uses it for ordinary comments.
  The patterns are regular expressions and replaceable (``TYPED_OUTPUT_PATTERNS``).
  Quarto's own chunk-option comments (``#| output: false``) do not match any
  default pattern, since ``|`` is not whitespace.
- **A hand-written output block**: a fence with no language, or ``text``/
  ``output``, placed right after a code fence of one of those languages, with
  only blank lines between the two. The finding is reported on the output
  block's opening fence.

Scope:
- **Whole tree by default** (``TYPED_OUTPUT_DIFF_SCOPED`` unset or false): every
  tracked file the globs match is scanned, so a full run measures how much
  typed output a corpus carries.
- **Diff-scoped on request** (``TYPED_OUTPUT_DIFF_SCOPED=true``): only findings on a
  line the diff since ``TYPED_OUTPUT_BASE_REF`` adds are reported -- for an output
  block, any added line of the block -- so a repo with legacy occurrences can
  adopt the check without every run reporting them. The diff is taken from
  the merge base of ``TYPED_OUTPUT_BASE_REF`` and ``HEAD``, the same anchor
  ``check-new-line-breaks`` uses, so a base branch that has advanced does not
  widen what is checked. When the diff cannot be computed (no base ref on a
  push run, or a shallow clone missing the base commit) the check is
  *skipped* with a warning rather than falling back to a whole-tree scan,
  which would report exactly the legacy occurrences diff-scoping exists to
  leave alone. A finding whose lines the same diff also deletes, contiguously
  and in order, is treated as moved rather than new, so splitting a chapter
  into subfiles does not report the output it relocates. For an output block
  those lines run from the code fence it follows through its closing fence,
  so a short output line such as ``1`` is never excused by an unrelated
  deletion of the same text.
- **Working-tree aware, diff-scoped runs only.** When a tracked file the
  globs match carries an uncommitted change, the diff is taken against the
  working tree instead of ``HEAD``, so a local run before committing examines
  the uncommitted lines too; CI's tree is always clean, so there it stays
  committed-only. An untracked file is not in any diff and is named in a
  warning instead.
- **Warn-only by default** (``TYPED_OUTPUT_FAIL`` defaults to false).

Configuration (environment variables, set by the composite action):
  TYPED_OUTPUT_PATTERNS      Newline-separated regular expressions for output
                    comments (default: the five forms above, in four
                    patterns). Blank lines are ignored; an invalid
                    expression is an error (exit 2), never skipped.
  TYPED_OUTPUT_GLOBS         Space-separated git pathspecs to check (default: '*.qmd').
  TYPED_OUTPUT_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  TYPED_OUTPUT_FAIL          "true" => exit 1 on findings; default "false".
  TYPED_OUTPUT_DIFF_SCOPED   "true" => report only lines added since TYPED_OUTPUT_BASE_REF.
  TYPED_OUTPUT_BASE_REF      Git ref/SHA to diff against in diff-scoped mode.
"""

import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

# Output-comment patterns. Each is searched for in every line of a code fence
# of one of CODE_LANGUAGES. `#\s*->` covers both `# ->` and `#->`.
DEFAULT_PATTERNS = [
    r"#\s*->",
    r"#\s*=>",
    r"#>",
    r"#\s*(?i:output):",
]

# Fence languages whose contents are code that prints output.
CODE_LANGUAGES = frozenset({"python", "r", "julia"})

# Info strings that make a fence read as an output block when it follows a
# code fence. The empty string is a fence with no language at all.
OUTPUT_LANGUAGES = frozenset({"", "text", "output"})

_DEFAULT_FAIL = False
_DEFAULT_GLOBS = "*.qmd"

_FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
_BLANK_RE = re.compile(r"^\s*$")
_EXEC_CHUNK_RE = re.compile(r"^\{\s*([A-Za-z][A-Za-z0-9_]*)")
_CLASS_LANG_RE = re.compile(r"(?:^\{|\s)\.([A-Za-z][A-Za-z0-9_+-]*)")


class Fence(NamedTuple):
    """How a fence's info string reads.

    ``language`` is lower-cased, and empty for a fence with no language;
    ``executable`` is True for a Quarto chunk (``{r}``), False for a plain
    fence (```` ```r ```` or ```` ```{.r} ````).
    """

    language: str
    executable: bool


def parse_info_string(info: str) -> Fence:
    """Classify a fence's info string.

    ``{r}``, ``{python echo=FALSE}`` and ``{r label}`` are executable chunks;
    ``{.python}``, ``{#lst-id .python}`` and ``{.numberLines .python}`` are
    plain fences whose class names the language (a code language wins over
    any other class, else the first class); ``{=html}`` is a raw block, which is neither
    code nor output; ``{#id}`` with no class has no language; anything else
    takes its first word.
    """
    info = info.strip()
    if info.startswith("{"):
        if info.startswith("{="):
            return Fence("{=raw}", False)
        m = _EXEC_CHUNK_RE.match(info)
        if m:
            return Fence(m.group(1).lower(), True)
        # Pandoc attribute form, `{#lst-id .python lst-cap="..."}`: a class
        # names the language, wherever it sits among the attributes. Prefer
        # a code language over a modifier class written ahead of it, as in
        # `{.numberLines .python}`.
        classes = [c.lower() for c in _CLASS_LANG_RE.findall(info)]
        for cls in classes:
            if cls in CODE_LANGUAGES:
                return Fence(cls, False)
        return Fence(classes[0] if classes else "", False)
    if not info:
        return Fence("", False)
    return Fence(info.split()[0].lower(), False)


class Finding(NamedTuple):
    """One flagged occurrence.

    ``line`` is the 1-based line reported; ``lines`` is every line the
    finding covers (the comment line alone, or an output block's opening
    fence through its closing fence), which diff scoping intersects with the
    added lines. ``span`` is what must have moved, contiguously, for the
    finding to count as relocated rather than new: the comment line alone,
    or for an output block, the code fence it follows through the block's
    closing fence.
    """

    line: int
    kind: str
    match: str
    lines: Tuple[int, ...]
    span: Tuple[int, ...]


class PatternError(ValueError):
    """A caller-supplied pattern is not a valid regular expression."""


def compile_patterns(patterns: List[str]) -> List["re.Pattern[str]"]:
    """Compile every pattern, refusing the whole set if any is invalid.

    Dropping a bad one instead would let a typo in a ``patterns`` override
    turn the comment detector off while the run still reports clean.
    """
    compiled = []
    for pat in patterns:
        try:
            compiled.append(re.compile(pat))
        except re.error as exc:
            raise PatternError(f"invalid pattern {pat!r}: {exc}") from None
    return compiled


def scan_text(text: str, patterns: List["re.Pattern[str]"]) -> List[Finding]:
    """Return every typed-output finding in one file's text.

    Fences are matched CommonMark-style: a fence closes on a line of the same
    character, at least as long, with nothing after it but whitespace, so a
    four-backtick fence quoting a three-backtick example is one block and its
    contents are not parsed as fences. An unclosed fence runs to the end of
    the file.

    Unlike CommonMark, a fence may be indented any amount rather than at most
    three spaces: CommonMark measures that cap from the enclosing container,
    and a code fence inside a list item is routinely indented four spaces or
    more from the margin, which a flat three-space cap would stop scanning.
    The cost is that a fence-shaped line inside an indented code block reads
    as a fence.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        # The empty string after a final newline is not a line of the file.
        lines.pop()
    findings: List[Finding] = []
    i = 0
    n = len(lines)
    # True after a code fence closes, until a non-blank line that is not an
    # output-block opener intervenes.
    after_code = False
    code_start = 0
    while i < n:
        m = _FENCE_RE.match(lines[i])
        if not m:
            if not _BLANK_RE.match(lines[i]):
                after_code = False
            i += 1
            continue
        marker = m.group(2)
        fence = parse_info_string(m.group(3))
        # A backtick fence's info string may not contain a backtick; such a
        # line is inline code, not a fence.
        if marker[0] == "`" and "`" in m.group(3):
            after_code = False
            i += 1
            continue
        start = i
        close_re = re.compile(
            r"^\s*" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}\s*$"
        )
        j = i + 1
        while j < n and not close_re.match(lines[j]):
            j += 1
        end = min(j, n - 1)
        is_code = fence.language in CODE_LANGUAGES
        if is_code:
            for k in range(start + 1, j):
                for pat in patterns:
                    hit = pat.search(lines[k])
                    if hit:
                        findings.append(Finding(
                            k + 1, "comment",
                            f"`{hit.group(0)}` in {lines[k].strip()}",
                            (k + 1,), (k + 1,),
                        ))
                        break
        elif after_code and not fence.executable and fence.language in OUTPUT_LANGUAGES:
            info = m.group(3).strip()
            findings.append(
                Finding(
                    start + 1,
                    "block",
                    f"{marker}{info}" if info else f"{marker} (no language)",
                    tuple(range(start + 1, end + 2)),
                    tuple(range(code_start + 1, end + 2)),
                )
            )
        if is_code:
            code_start = start
        after_code = is_code
        i = j + 1
    return findings


# ── Scope resolution (the approach check-new-line-breaks uses) ───────────────

def _run_git(args: List[str]) -> Optional[str]:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, check=True,
            encoding="utf-8", errors="replace",
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


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


def compile_ignores(patterns: List[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def _ignored(rel: str, ignores: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in ignores)


def _status_path(line: str) -> str:
    rest = line[3:]
    if " -> " in rest:
        rest = rest.split(" -> ", 1)[1]
    return rest.strip().strip('"')


def _has_uncommitted_changes(
    pathspecs: List[str], ignores: List["re.Pattern[str]"]
) -> bool:
    """True when a tracked file the pathspecs match carries a staged or
    unstaged change. Untracked files are excluded: ``git diff`` cannot show
    them, so they must not flip the scope (see ``_untracked_matches``)."""
    out = _run_git(["status", "--porcelain", "-uno", "--", *pathspecs])
    if not out:
        return False
    return any(
        line and not _ignored(_status_path(line), ignores)
        for line in out.splitlines()
    )


def _untracked_matches(
    pathspecs: List[str], ignores: List["re.Pattern[str]"]
) -> List[str]:
    out = _run_git(["status", "--porcelain", "-uall", "--", *pathspecs])
    if not out:
        return []
    return sorted(
        _status_path(line)
        for line in out.splitlines()
        if line.startswith("??") and not _ignored(_status_path(line), ignores)
    )


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def added_lines(
    base_ref: str,
    pathspecs: List[str],
    worktree: bool,
    ignores: Optional[List["re.Pattern[str]"]] = None,
) -> Optional[Tuple[Dict[str, Set[int]], List[List[str]]]]:
    """Return ({file: added line numbers}, deleted runs) for the diff from the
    merge base of ``base_ref`` and HEAD, or None when it cannot be computed.
    ``worktree`` diffs against the working tree instead of HEAD. A deleted
    run is one maximal stretch of consecutive deleted lines, in order; lines
    deleted from a file ``ignores`` covers are not collected, since content
    outside the checked population cannot have moved from it."""
    merge_base = (_run_git(["merge-base", base_ref, "HEAD"]) or "").strip()
    if not merge_base:
        return None
    target = [merge_base] if worktree else [f"{merge_base}..HEAD"]
    # --no-renames: a rename then reads as a deletion plus an addition, so a
    # file moved in from an ignored path is examined, and one moved within
    # the checked population is exempted by the moved-span match below.
    diff = _run_git(["diff", "--unified=0", "--no-color", "--no-renames", *target, "--", *pathspecs])
    if diff is None:
        return None
    result: Dict[str, Set[int]] = {}
    runs: List[List[str]] = []
    run_open = False
    old_ignored = False
    cur: Optional[str] = None
    lineno = 0
    in_hunk = False
    for raw in diff.splitlines():
        if raw.startswith("diff "):
            in_hunk = False
            run_open = False
            continue
        if not in_hunk and raw.startswith("--- "):
            source = raw[4:]
            old_ignored = source != "/dev/null" and _ignored(source[2:], ignores or [])
            continue
        if not in_hunk and raw.startswith("+++ "):
            target_path = raw[4:]
            cur = None if target_path == "/dev/null" else target_path[2:]
            if cur is not None:
                result.setdefault(cur, set())
            continue
        if raw.startswith("@@"):
            in_hunk = True
            run_open = False
            m = _HUNK_RE.match(raw)
            lineno = int(m.group(1)) if m else 0
            continue
        if not in_hunk:
            continue
        if raw.startswith("-"):
            if old_ignored:
                continue
            if not run_open:
                runs.append([])
                run_open = True
            runs[-1].append(raw[1:])
        elif raw.startswith("+"):
            run_open = False
            if cur is not None:
                result[cur].add(lineno)
            lineno += 1
    return result, runs


def take_moved(runs: List[List[str]], block: List[str]) -> bool:
    """Remove one contiguous occurrence of ``block`` from the deleted runs
    and return True, or return False when no run contains it. Removing it
    means one deletion excuses at most one addition."""
    k = len(block)
    for idx, run in enumerate(runs):
        for s in range(len(run) - k + 1):
            if run[s:s + k] == block:
                runs[idx:idx + 1] = [run[:s], run[s + k:]]
                return True
    return False


def tracked_files(pathspecs: List[str]) -> List[str]:
    out = _run_git(["ls-files", "-z", "--", *pathspecs])
    if out is None:
        return []
    return sorted(p for p in out.split("\0") if p)


class Result(NamedTuple):
    findings: List[Tuple[str, Finding]]
    skipped: bool
    examined_files: int


def run(
    globs: List[str],
    ignores: List["re.Pattern[str]"],
    patterns: List["re.Pattern[str]"],
    diff_scoped: bool = False,
    base_ref: str = "",
) -> Result:
    scope: Optional[Dict[str, Set[int]]] = None
    moved_runs: List[List[str]] = []
    if diff_scoped:
        if not base_ref:
            return Result([], True, 0)
        worktree = _has_uncommitted_changes(globs, ignores)
        scoped = added_lines(base_ref, globs, worktree, ignores)
        if scoped is None:
            return Result([], True, 0)
        scope, moved_runs = scoped
        untracked = _untracked_matches(globs, ignores)
        if untracked:
            print(
                f"::warning::{len(untracked)} untracked file(s) match the glob "
                "but are not examined (git diff cannot see untracked content; "
                "run `git add` to include them): " + ", ".join(untracked)
            )
        print(
            f"Checking lines added since {base_ref[:12]} "
            f"(scope: {'working tree' if worktree else 'committed'}).\n"
        )
        files = sorted(scope)
    else:
        print("Checking every tracked file the globs match (whole tree).\n")
        files = tracked_files(globs)

    out: List[Tuple[str, Finding]] = []
    examined = 0
    for rel in files:
        if _ignored(rel, ignores):
            continue
        path = Path(rel)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        examined += 1
        lines = text.split("\n")
        for finding in scan_text(text, patterns):
            if scope is not None:
                new = [
                    ln for ln in finding.lines
                    if ln in scope[rel] and 1 <= ln <= len(lines)
                ]
                if not new:
                    continue
                # Moved-not-new: the finding's whole span -- for an output
                # block, the code fence it follows through its closing fence
                # -- is added, and the same lines were deleted contiguously
                # elsewhere in this diff, so it was relocated. Matching the
                # span rather than line by line keeps a short output line
                # such as `1` or `TRUE` from being excused by an unrelated
                # deletion of the same text.
                span_added = all(ln in scope[rel] for ln in finding.span)
                if span_added and take_moved(
                    moved_runs, [lines[ln - 1] for ln in finding.span]
                ):
                    continue
            out.append((rel, finding))
    return Result(out, False, examined)


# ── Main ─────────────────────────────────────────────────────────────────

def _split_list(value: str) -> List[str]:
    return [tok.strip() for tok in re.split(r"[,\n]", value or "") if tok.strip()]


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw not in ("true", "false"):
        print(f"::warning::{name}={raw!r} is not 'true' or 'false'; using default ({default}).")
        return default
    return raw == "true"


_MESSAGES = {
    "comment": "Typed output: a comment stands in for printed output; "
               "run the code in an executable chunk instead",
    "block": "Typed output: a hand-written output block follows a code fence; "
             "run the code in an executable chunk instead",
}


def main() -> int:
    raw_patterns = os.environ.get("TYPED_OUTPUT_PATTERNS", "")
    pattern_list = [p.strip() for p in raw_patterns.split("\n") if p.strip()]
    try:
        patterns = compile_patterns(pattern_list or DEFAULT_PATTERNS)
    except PatternError as exc:
        print(f"::error::check-typed-output: {exc}; refusing to run rather "
              "than check with fewer patterns than configured.")
        return 2
    globs = os.environ.get("TYPED_OUTPUT_GLOBS", _DEFAULT_GLOBS).split() or [_DEFAULT_GLOBS]
    ignores = compile_ignores(_split_list(os.environ.get("TYPED_OUTPUT_PATHS_IGNORE", "")))
    fail = _env_flag("TYPED_OUTPUT_FAIL", _DEFAULT_FAIL)
    diff_scoped = _env_flag("TYPED_OUTPUT_DIFF_SCOPED", False)
    base_ref = os.environ.get("TYPED_OUTPUT_BASE_REF", "").strip()

    result = run(globs, ignores, patterns, diff_scoped, base_ref)
    if result.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(
            f"::warning::Skipping the typed-output check for this run "
            f"({reason}; diff-scoped mode does not fall back to a whole-tree "
            f"scan, which would report pre-existing occurrences)."
        )
        return 0

    print(f"Examined {result.examined_files} file(s).")
    if not result.findings:
        print("No typed output found.")
        return 0

    severity = "error" if fail else "warning"
    per_file: "Counter[str]" = Counter()
    for rel, f in result.findings:
        per_file[rel] += 1
        preview = f.match if len(f.match) <= 100 else f.match[:97] + "..."
        print(f"::{severity} file={rel},line={f.line}::{_MESSAGES[f.kind]}: {preview}")

    print("\nFindings per file:")
    for rel, count in sorted(per_file.items()):
        print(f"  {count:4d}  {rel}")
    print(
        f"\n{len(result.findings)} typed-output finding(s) in {len(per_file)} file(s). "
        "Show output by running the code as an executable {r}/{python} chunk."
    )
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
