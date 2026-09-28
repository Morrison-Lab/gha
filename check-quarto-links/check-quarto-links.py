#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""
Flag relative links, in tracked Quarto/Markdown sources, to pages that do not
exist -- without rendering anything.

Why this exists: Quarto does not fail a render over a link to a missing page.
It prints ``WARN: Unable to resolve link target: chapters/old-name.qmd`` and
carries on, so a page renamed or deleted months ago leaves dead links behind
while every check stays green. ``check-links`` (lychee) does not see them
either: lychee chooses a parser by file extension and reads ``.qmd`` as plain
text, so it extracts only absolute URLs and never checks a relative
``[text](other-page.qmd)`` (measured with lychee 0.24.2, 2026-09-28).

Design notes:

- **Source level, whole tree.** Every tracked file matching ``QL_GLOBS`` is
  read and every relative link in it whose target has one of
  ``QL_TARGET_EXTENSIONS`` is resolved against the filesystem. A dead link
  committed long ago is still a live defect, and one that costs one edit to
  clear, so there is no diff scoping (the same reasoning as
  ``check-junk-files``).
- **Include-aware.** Quarto splices ``{{< include path >}}`` files into the
  including page before it resolves links, so a link inside a ``_``-prefixed
  subfile is written relative to the page that includes it, not to the
  subfile's own directory. A link is therefore accepted when it resolves
  from the file's own directory *or* from the directory of any page that
  includes it, directly or transitively.
- **Root-relative links** (``/about.qmd``) resolve against the Quarto
  project directory: the nearest ancestor holding ``_quarto.yml`` (or
  ``_quarto.yaml``), else the repository root.
- **What is not a link.** Fenced code blocks, inline code spans and HTML
  comments are blanked out before matching (line numbers are preserved), so
  an example link in a code block or an outtake commented out of a page is
  not reported. URLs with a scheme (``https:``, ``mailto:``), protocol-
  relative ``//`` URLs, pure ``#anchors``, and targets containing a
  shortcode or template expression (``{{``, ``{%``, ``${``) are skipped.
- **Search space is reported**, so a run that examined nothing reads
  differently from a clean pass.

Configuration (environment variables, set by the composite action):
  QL_GLOBS              Space-separated git pathspecs of tracked source files
                        to scan (default: '*.qmd *.md *.Rmd').
  QL_TARGET_EXTENSIONS  Comma/space-separated target extensions to verify
                        (default: '.qmd, .md, .Rmd, .ipynb').
  QL_PATHS_IGNORE       Comma/newline-separated globs (``*``, ``?``, ``**``)
                        of source files to skip.
  QL_FAIL               Only an explicit 'false' makes findings non-blocking.
"""

import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, NamedTuple, Optional, Set
from urllib.parse import unquote

DEFAULT_GLOBS = "*.qmd *.md *.Rmd"
DEFAULT_TARGET_EXTENSIONS = ".qmd, .md, .Rmd, .ipynb"
PROJECT_FILES = ("_quarto.yml", "_quarto.yaml")

# ``](target)`` or ``](target "title")`` or ``](<target with spaces>)``; the
# ``]`` and ``(`` may be separated from the link text by a line break, which
# is why matching runs over the whole file rather than line by line.
_INLINE_LINK_RE = re.compile(r"\]\(\s*(<[^>\n]+>|[^)\s]+)")
# ``[label]: target`` reference definitions.
_REF_DEF_RE = re.compile(r"^[ ]{0,3}\[(?!\^)[^\]\n]+\]:[ \t]*(<[^>\n]+>|\S+)", re.M)
# Raw HTML ``href="..."`` / ``src="..."``.
_HTML_ATTR_RE = re.compile(r"""\b(?:href|src)\s*=\s*(["'])([^"'\n]+)\1""", re.I)
# ``{{< include path >}}``; the escaped ``{{</* include */>}}`` form does not
# match, because ``/*`` follows ``<``.
_INCLUDE_RE = re.compile(r"\{\{<\s*include\s+([^\s>]+)\s*>\}\}")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_CODE_SPAN_RE = re.compile(r"(`+)(?!`).*?(?<!`)\1(?!`)")


class Finding(NamedTuple):
    path: str
    line: int
    target: str


def _run_git(args: List[str], cwd: Optional[Path] = None) -> Optional[str]:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, check=True,
            encoding="utf-8", errors="replace", cwd=cwd,
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


def compile_ignores(patterns: Iterable[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def split_list(value: str) -> List[str]:
    return [tok.strip() for tok in re.split(r"[,\s]+", value or "") if tok.strip()]


def blank_non_prose(text: str) -> str:
    """Replace code blocks, code spans and HTML comments with spaces.

    Newlines are kept, so an offset into the result maps to the same line
    number as in the original.
    """
    def _blank(m: "re.Match[str]") -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    text = _COMMENT_RE.sub(_blank, text)
    lines = text.split("\n")
    fence: Optional[str] = None
    for i, line in enumerate(lines):
        m = _FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
                lines[i] = " " * len(line)
        else:
            stripped = line.strip()
            if m and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                fence = None
            lines[i] = " " * len(line)
    text = "\n".join(lines)
    return _CODE_SPAN_RE.sub(_blank, text)


def extract_links(text: str) -> List[tuple]:
    """Return ``(line_number, raw_target)`` for every link-like target."""
    prose = blank_non_prose(text)
    found = []
    for m in _INLINE_LINK_RE.finditer(prose):
        found.append((m.start(1), m.group(1)))
    for m in _REF_DEF_RE.finditer(prose):
        found.append((m.start(1), m.group(1)))
    for m in _HTML_ATTR_RE.finditer(prose):
        found.append((m.start(2), m.group(2)))
    found.sort()
    return [(prose.count("\n", 0, off) + 1, raw) for off, raw in found]


def normalize_target(raw: str, extensions: Set[str]) -> Optional[str]:
    """The path part of ``raw`` when it is a local page link to verify."""
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if not target or target.startswith("#") or target.startswith("//"):
        return None
    if _SCHEME_RE.match(target):
        return None
    if any(tok in target for tok in ("{{", "{%", "${", "`r ")):
        return None
    target = re.split(r"[#?]", target, maxsplit=1)[0]
    target = unquote(target)
    if not target or target.endswith("/"):
        return None
    if PurePosixPath(target).suffix.lower() not in extensions:
        return None
    return target


def project_root(rel_dir: PurePosixPath, root: Path, tracked: Set[str]) -> PurePosixPath:
    """Nearest ancestor of ``rel_dir`` (inclusive) holding ``_quarto.yml``."""
    for cand in [rel_dir, *rel_dir.parents]:
        for name in PROJECT_FILES:
            rel = (cand / name).as_posix()
            if rel.startswith("./"):
                rel = rel[2:]
            if rel in tracked or (root / cand / name).is_file():
                return cand
    return PurePosixPath(".")


def build_includers(texts: Dict[str, str], root: Path) -> Dict[str, Set[str]]:
    """Map each included file to the set of files that include it."""
    includers: Dict[str, Set[str]] = {}
    tracked = set(texts)
    for path, text in texts.items():
        here = PurePosixPath(path).parent
        for m in _INCLUDE_RE.finditer(text):
            inc = m.group(1).strip("\"'")
            if inc.startswith("/"):
                base = project_root(here, root, tracked)
                inc_path = base / inc.lstrip("/")
            else:
                inc_path = here / inc
            key = os.path.normpath(inc_path.as_posix())
            includers.setdefault(key, set()).add(path)
    return includers


def is_partial(path: str) -> bool:
    """True for a file Quarto never renders on its own.

    Quarto skips files and directories whose names start with ``_`` or ``.``
    when it renders a project; such a file only reaches a page through an
    include.
    """
    return any(part.startswith(("_", ".")) for part in PurePosixPath(path).parts)


def base_dirs(path: str, includers: Dict[str, Set[str]]) -> List[PurePosixPath]:
    """The file's own directory plus every transitive includer's directory."""
    seen = {path}
    stack = [path]
    dirs = []
    while stack:
        cur = stack.pop()
        d = PurePosixPath(cur).parent
        if d not in dirs:
            dirs.append(d)
        for parent in includers.get(os.path.normpath(cur), ()):
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return dirs


def find_dead_links(
    root: Path,
    files: List[str],
    extensions: Set[str],
    all_tracked: Optional[Set[str]] = None,
    skipped: Optional[List[str]] = None,
) -> List[Finding]:
    """Scan ``files`` (repo-relative) under ``root`` for dead page links.

    Partial files (see ``is_partial``) that no scanned file includes are
    appended to ``skipped`` instead of being checked.
    """
    if skipped is None:
        skipped = []
    texts: Dict[str, str] = {}
    for rel in files:
        try:
            texts[rel] = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    tracked = set(all_tracked or ()) | set(texts)
    includers = build_includers(texts, root)
    findings = []
    for rel, text in texts.items():
        if is_partial(rel) and os.path.normpath(rel) not in includers:
            # Quarto never renders a ``_``-prefixed file on its own, and with
            # no page including it there is no directory its links would be
            # resolved from -- an outtake kept for reuse, typically.
            skipped.append(rel)
            continue
        dirs = base_dirs(rel, includers)
        for line, raw in extract_links(text):
            target = normalize_target(raw, extensions)
            if target is None:
                continue
            if target.startswith("/"):
                cands = [project_root(d, root, tracked) / target.lstrip("/") for d in dirs]
            else:
                cands = [d / target for d in dirs]
            if not any((root / c).exists() for c in cands):
                findings.append(Finding(rel, line, raw.strip()))
    return findings


def tracked_files(globs: List[str], ignores: List["re.Pattern[str]"]) -> Optional[List[str]]:
    out = _run_git(["ls-files", "-z", "--", *globs])
    if out is None:
        return None
    files = [f for f in out.split("\0") if f]
    return sorted(f for f in files if not any(r.match(f) for r in ignores))


def _escape_annotation(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main() -> int:
    globs = (os.environ.get("QL_GLOBS") or DEFAULT_GLOBS).split()
    exts = {
        e.lower() if e.startswith(".") else "." + e.lower()
        for e in split_list(os.environ.get("QL_TARGET_EXTENSIONS") or DEFAULT_TARGET_EXTENSIONS)
    }
    ignores = compile_ignores(
        t.strip() for t in re.split(r"[,\n]", os.environ.get("QL_PATHS_IGNORE", "")) if t.strip()
    )
    fail = os.environ.get("QL_FAIL", "true").strip().lower() != "false"

    files = tracked_files(globs, ignores)
    if files is None:
        print("::error::check-quarto-links: `git ls-files` failed; is this a git checkout?")
        return 1
    all_out = _run_git(["ls-files", "-z"]) or ""
    all_tracked = {f for f in all_out.split("\0") if f}
    skipped: List[str] = []
    findings = find_dead_links(Path("."), files, exts, all_tracked, skipped)

    print(
        f"Examined {len(files) - len(skipped)} file(s) matching {' '.join(globs)} "
        f"for links to {', '.join(sorted(exts))} targets."
    )
    if skipped:
        print(
            f"Skipped {len(skipped)} `_`-prefixed file(s) that no scanned page "
            "includes, since Quarto never renders them: " + ", ".join(skipped)
        )
    level = "error" if fail else "warning"
    for f in findings:
        print(
            f"::{level} file={f.path},line={f.line},title=Link to a missing page::"
            f"{_escape_annotation(f.target)} does not exist"
        )
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## Links to missing pages\n\n")
            if findings:
                fh.write("| File | Line | Target |\n|---|---|---|\n")
                for f in findings:
                    fh.write(f"| `{f.path}` | {f.line} | `{f.target}` |\n")
            else:
                fh.write(f"None found in {len(files)} file(s).\n")
    if findings:
        print(
            f"{len(findings)} link(s) to missing pages. Point each at the page's "
            "current name, or remove the link. Quarto only warns about these "
            "('Unable to resolve link target'), so the render stays green."
        )
        return 1 if fail else 0
    print("No links to missing pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
