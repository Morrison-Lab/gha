#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Flag a technical term whose first use in a passage is not linked to its definition.

The rule this enforces (Ezra, 2026-10-16; ai-config#4553, psw#223, psw#227): every
technical term is hyperlinked to its formal definition the first time it appears
in each div, or in each prose paragraph outside a div, and a term with no formal
definition gets one (gha#1078).

Which words are terms: the check learns them from the corpus itself.
1. Each `::: {#def-...}` div contributes its title (any heading inside it) and its
   bold terms, with parenthetical aliases ("also called" glosses) split out.
2. Each link whose target ends in `#def-...` contributes its link text, so a term
   defined on another site (`[risk](https://example.com/ch.html#def-risk)`) is known once
   anyone links it.
3. `--terms-file` adds terms by hand, one per line.

Findings:
- `unlinked-first-use`: the first occurrence of a known term in a passage is plain
  text, not inside a link or an `@def-...` cross-reference. The term's own def div
  is skipped.
- `no-definition`: a bold term in a passage that is not a def div, and that
  matches no known term, so it is introduced as technical with no definition
  anywhere in the corpus. Give it a `#def-` div.

Skipped: code fences and spans, math, HTML comments, YAML front matter, include
shortcodes, headings, images, and the `(...)` of a link.

Opt-outs: `<!-- check-term-links: allow -->` on a line skips that line;
`<!-- check-term-links: ignore-file -->` skips a file; `--allow-file` names terms
that are ordinary English in this corpus.

Scope: only a finding on a line a diff adds is reported (`--base-ref`, `--diff`),
so adopting the check does not reflag the corpus. `--whole-tree` reports every
finding, to measure a corpus. With no base and no `--whole-tree`, the check
skips with a warning rather than widening to the whole tree.
"""

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd"
DEFAULT_PATHS_IGNORE = ""

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
DIV_OPEN_RE = re.compile(r"^(?P<fence>:{3,})\s*(?P<attrs>\{[^}]*\}|\S.*)?$")
DIV_CLOSE_RE = re.compile(r"^(?P<fence>:{3,})\s*$")
DEF_ID_RE = re.compile(r"#(?P<id>def-[A-Za-z0-9_-]+)")
HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*(?:\{[^}]*\})?\s*$")
FILE_OPT_OUT_RE = re.compile(r"<!--\s*check-term-links:\s*ignore-file\s*-->", re.I)
LINE_OPT_OUT_RE = re.compile(r"<!--\s*check-term-links:\s*(?:allow|ignore)\s*-->", re.I)

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
DISPLAY_MATH_RE = re.compile(r"\$\$.*?\$\$", re.S)
INLINE_MATH_RE = re.compile(r"(?<![\\$])\$(?!\s)(?:[^$\\\n]|\\.)+?(?<!\s)\$(?![\d$])")
SHORTCODE_RE = re.compile(r"\{\{<.*?>\}\}", re.S)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)(?:\{[^}]*\})?")
ATTR_RE = re.compile(r"\{[^{}\n]*\}")
CITATION_RE = re.compile(r"\[[^\[\]]*@[^\[\]]*\]")
# A bare URL, not the target of a `[text](url)` link, which the scan blanks after it finds the links.
URL_RE = re.compile(r"<https?://[^>]+>|(?<![(\[])https?://[^\s)]+")
LINK_TARGET_RE = re.compile(r"(?<=\])(?:\([^)]*\)|\[[^\]]*\])")
# [text](url) and [text][ref]; group "text" is what a reader clicks.
LINK_RE = re.compile(r"\[(?P<text>[^\[\]]+)\](?:\((?P<url>[^)\s]*)[^)]*\)|\[[^\]]*\])")
CROSSREF_RE = re.compile(r"@(?:def|thm|lem|cor|prp|cnj|exm|rem|sec)-[A-Za-z0-9_-]+")
FOLLOWING_CROSSREF_RE = re.compile(r"(?:\*\*|__)?\s*\(\s*@def-[A-Za-z0-9_-]+\s*\)")
BOLD_RE =re.compile(r"\*\*(?P<term>[^*\n]+?)\*\*|__(?P<term2>[^_\n]+?)__")

COMMON_LABELS = frozenset({
    "note", "warning", "caution", "tip", "important", "example", "remark",
    "definition", "step", "case", "proof", "solution", "answer", "question",
    "summary", "recap", "prerequisite", "prerequisites", "todo", "fixme",
    "exercise", "hint", "why", "how", "what", "when", "where", "goal",
})
# Bold used for emphasis on a function word, which no definition div would cover.
EMPHASIS_WORDS = frozenset({
    "not", "once", "and", "or", "if", "then", "all", "any", "each", "every", "only",
    "both", "either", "neither", "never", "always", "must", "cannot", "can", "does",
    "same", "different", "before", "after", "twice", "exactly", "nothing", "none",
    "before", "without", "with", "than", "more", "less", "most", "least", "one",
    "two", "three", "first", "second", "third", "last", "next", "also", "too",
})
LEADING_ARTICLE_RE =re.compile(r"^(?:the|a|an)\s+", re.I)
MIN_TERM_LEN = 3
MAX_TERM_WORDS = 5


@dataclass(frozen=True)
class Finding:
    file: Path
    line: int
    rule: str
    term: str
    message: str


@dataclass
class Passage:
    """Consecutive prose lines that form one 'first use' scope."""

    div_id: Optional[str]
    in_div: bool
    lines: List[Tuple[int, str]]  # (1-based line number, masked text)


def term_key(term: str) -> str:
    """Normalize a term for lookup: lowercase, articles dropped, runs of space and hyphen folded."""
    t = LEADING_ARTICLE_RE.sub("", term.strip().strip("*_\"'“”‘’").strip())
    t = re.sub(r"[\s\-]+", " ", t).lower()
    return t


def lookup(text: str, terms: Dict[str, Set[str]]) -> Optional[str]:
    """The key of the known term `text` names, allowing a plural, or None."""
    key = term_key(text)
    if key in terms:
        return key
    for suffix in ("es", "s"):
        if key.endswith(suffix) and key[: -len(suffix)] in terms:
            return key[: -len(suffix)]
    return None


def usable_term(term: str, allowed_out: Set[str]) -> bool:
    key = term_key(term)
    if len(key) < MIN_TERM_LEN or len(key.split()) > MAX_TERM_WORDS:
        return False
    if key in COMMON_LABELS or key in allowed_out:
        return False
    # Words only: a term with math, a colon or other markup is not a prose term.
    return re.fullmatch(r"[a-z][a-z0-9' \-]*", key) is not None


def mask_inline(text: str) -> str:
    """Blank spans that are not prose, keeping every offset and newline in place."""

    def blank(m: "re.Match[str]") -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    for rx in (COMMENT_RE, DISPLAY_MATH_RE, INLINE_CODE_RE, INLINE_MATH_RE,
               SHORTCODE_RE, IMAGE_RE, URL_RE):
        text = rx.sub(blank, text)
    # `ATTR_RE` last: `{...}` after a link or a header is markup, never prose.
    return ATTR_RE.sub(blank, text)


def preprocess(lines: Sequence[str]) -> Tuple[List[str], Set[int]]:
    """Return each line with front matter, code fences and comments blanked, and the opted-out line numbers."""
    out: List[str] = []
    opted: Set[int] = set()
    in_yaml = False
    fence = ""
    in_comment = False
    for idx, raw in enumerate(lines, start=1):
        if idx == 1 and raw.strip() == "---":
            in_yaml = True
            out.append("")
            continue
        if in_yaml:
            in_yaml = raw.strip() not in ("---", "...")
            out.append("")
            continue
        m = FENCE_RE.match(raw)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = ""
            out.append("")
            continue
        if m and not in_comment:
            fence = m.group(1)
            out.append("")
            continue
        if LINE_OPT_OUT_RE.search(raw):
            opted.add(idx)
        line = raw
        if in_comment:
            end = line.find("-->")
            if end == -1:
                out.append("")
                continue
            line = " " * (end + 3) + line[end + 3:]
            in_comment = False
        # Drop closed comments, then an unterminated one that runs to the end of the line.
        line = COMMENT_RE.sub(lambda mm: " " * len(mm.group(0)), line)
        start = line.find("<!--")
        if start != -1:
            line = line[:start]
            in_comment = True
        out.append(line)
    return out, opted


def split_passages(masked: Sequence[str]) -> List[Passage]:
    """Cut a file into passages: one per div (between div fences), one per paragraph outside divs."""
    passages: List[Passage] = []
    stack: List[Tuple[int, Optional[str]]] = []  # (fence length, def id or None)
    cur: List[Tuple[int, str]] = []

    def flush() -> None:
        nonlocal cur
        if cur:
            div_id = next((d for _, d in reversed(stack) if d), None) if stack else None
            passages.append(Passage(div_id=div_id, in_div=bool(stack), lines=cur))
        cur = []

    for idx, line in enumerate(masked, start=1):
        s = line.strip()
        m_close = DIV_CLOSE_RE.match(s)
        m_open = None if m_close else DIV_OPEN_RE.match(s)
        if m_open:
            flush()
            attrs = m_open.group("attrs") or ""
            d = DEF_ID_RE.search(attrs)
            stack.append((len(m_open.group("fence")), d.group("id") if d else None))
            continue
        if m_close:
            flush()
            if stack and len(m_close.group("fence")) >= stack[-1][0]:
                stack.pop()
            continue
        if HEADING_RE.match(s):
            flush()
            continue
        if not s and not stack:
            flush()
            continue
        if s:
            cur.append((idx, line))
    flush()
    return passages


def harvest_terms(
    masked: Sequence[str], allowed_out: Set[str]
) -> Dict[str, Set[str]]:
    """Map term key -> def ids it defines, from def-div titles and bold terms, and from links to `#def-` anchors."""
    terms: Dict[str, Set[str]] = {}

    def add(term: str, def_id: str) -> None:
        for piece in re.split(r"\s*(?:,|;|\bor\b|\balso called\b|\bknown as\b)\s*", term):
            piece = re.sub(r"\([^)]*\)", "", piece).strip()
            if usable_term(piece, allowed_out):
                terms.setdefault(term_key(piece), set()).add(def_id)

    stack: List[Tuple[int, Optional[str]]] = []
    for line in masked:
        s = line.strip()
        m_close = DIV_CLOSE_RE.match(s)
        m_open = None if m_close else DIV_OPEN_RE.match(s)
        if m_open:
            d = DEF_ID_RE.search(m_open.group("attrs") or "")
            stack.append((len(m_open.group("fence")), d.group("id") if d else None))
            continue
        if m_close:
            if stack and len(m_close.group("fence")) >= stack[-1][0]:
                stack.pop()
            continue
        def_id = next((d for _, d in reversed(stack) if d), None)
        if def_id:
            h = HEADING_RE.match(s)
            if h:
                add(mask_inline(h.group("title")), def_id)
            else:
                for b in BOLD_RE.finditer(mask_inline(line)):
                    add(b.group("term") or b.group("term2"), def_id)
        for lm in LINK_RE.finditer(mask_inline(line)):
            url = lm.group("url") or ""
            frag = re.search(r"#(def-[A-Za-z0-9_-]+)$", url)
            if frag:
                add(lm.group("text"), frag.group(1))
    return terms


def term_regex(keys: Sequence[str]) -> "re.Pattern[str]":
    """One alternation, longest term first, matching a term with an optional plural and flexible spacing."""
    parts = []
    for key in sorted(keys, key=len, reverse=True):
        words = [re.escape(w) for w in key.split()]
        parts.append(r"[\s\-]+".join(words))
    return re.compile(
        r"(?<![\w\-])(?:" + "|".join(parts) + r")(?:e?s)?(?![\w\-])", re.I
    )


def scan_passage(
    path: Path,
    passage: Passage,
    terms: Dict[str, Set[str]],
    rx: Optional["re.Pattern[str]"],
    opted: Set[int],
    added: Optional[Set[int]],
) -> List[Finding]:
    findings: List[Finding] = []
    line_of: List[int] = []  # offset -> 1-based line number
    chunks: List[str] = []
    for n, text in passage.lines:
        chunks.append(text + "\n")
        line_of.extend([n] * (len(text) + 1))
    text = mask_inline("".join(chunks))

    def line_at(offset: int) -> int:
        return line_of[min(offset, len(line_of) - 1)]

    # A citation `[@key]` and a crossref are not prose; the crossref also counts as a link.
    link_spans = [m.span() for m in LINK_RE.finditer(text)]
    link_spans += [m.span() for m in CROSSREF_RE.finditer(text)]
    prose = CITATION_RE.sub(lambda m: " " * len(m.group(0)), text)
    prose = LINK_TARGET_RE.sub(lambda m: " " * len(m.group(0)), prose)

    def reportable(n: int) -> bool:
        return n not in opted and (added is None or n in added)

    seen: Set[str] = set()
    if rx is not None:
        for m in rx.finditer(prose):
            key = lookup(m.group(0), terms)
            if key is None:
                continue
            if key in seen:
                continue
            seen.add(key)
            if passage.div_id and passage.div_id in terms[key]:
                continue
            start = m.start()
            if any(a <= start < b for a, b in link_spans):
                continue
            # "term (@def-term)" links the term it follows.
            if FOLLOWING_CROSSREF_RE.match(prose, m.end()):
                continue
            n = line_at(start)
            if not reportable(n):
                continue
            findings.append(Finding(
                file=path, line=n, rule="unlinked-first-use", term=key,
                message=(
                    f"'{m.group(0)}' is a defined term; link its first use in this "
                    f"{'div' if passage.in_div else 'paragraph'} to its definition."
                ),
            ))

    # A bold term in a non-def passage that no def anywhere covers.
    if not (passage.div_id and passage.div_id.startswith("def-")):
        for b in BOLD_RE.finditer(prose):
            term = b.group("term") or b.group("term2")
            end = b.end()
            if prose[end:end + 1] == ":" or not usable_term(term, EMPHASIS_WORDS):
                continue
            key = term_key(term)
            if lookup(term, terms) is not None:
                continue
            n = line_at(b.start())
            if not reportable(n):
                continue
            findings.append(Finding(
                file=path, line=n, rule="no-definition", term=key,
                message=(
                    f"Bold term '{term.strip()}' has no definition div anywhere in "
                    "the corpus; give it a `#def-` div and link to it."
                ),
            ))
    return findings


def scan_file(
    path: Path,
    lines: Sequence[str],
    terms: Dict[str, Set[str]],
    rx: Optional["re.Pattern[str]"],
    added: Optional[Set[int]],
) -> List[Finding]:
    if FILE_OPT_OUT_RE.search("\n".join(lines)):
        return []
    masked, opted = preprocess(lines)
    findings: List[Finding] = []
    for passage in split_passages(masked):
        findings.extend(scan_passage(path, passage, terms, rx, opted, added))
    return sorted(findings, key=lambda f: (f.line, f.rule, f.term))


def parse_added_lines(diff_text: str, repo_root: Path) -> Dict[Path, Set[int]]:
    """Added line numbers per file from a `git diff -U0` text."""
    added: Dict[Path, Set[int]] = {}
    current: Optional[Path] = None
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current = repo_root / line[6:].strip()
            added.setdefault(current, set())
        elif line.startswith("@@ ") and current is not None:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                added[current].update(range(start, start + count))
    return added


def diff_added_lines(
    base_ref: str, repo_root: Path, globs: Sequence[str]
) -> Optional[Dict[Path, Set[int]]]:
    """Lines added between the merge base with `base_ref` and the working tree, or None if git cannot say."""
    mb = subprocess.run(
        ["git", "merge-base", base_ref, "HEAD"], cwd=repo_root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if mb.returncode != 0 or not mb.stdout.strip():
        return None
    diff = subprocess.run(
        ["git", "diff", "-U0", mb.stdout.strip(), "--", *globs], cwd=repo_root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if diff.returncode != 0:
        return None
    return parse_added_lines(diff.stdout, repo_root)


def glob_to_regex(pat: str) -> "re.Pattern[str]":
    pat = pat.strip().strip("/")
    out = ""
    i = 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pat.startswith("**", i):
            out += ".*"
            i += 2
        elif pat[i] == "*":
            out += "[^/]*"
            i += 1
        elif pat[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pat[i])
            i += 1
    return re.compile(r"^" + out + r"(?:/.*)?$")


def read_term_list(path: str) -> Set[str]:
    """Keys from a one-term-per-line file; blank lines and `#` comments are skipped."""
    if not path:
        return set()
    p = Path(path)
    if not p.is_file():
        print(f"::warning::check-term-links: terms/allow file '{path}' not found.", file=sys.stderr)
        return set()
    keys = set()
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        t = raw.split("#", 1)[0].strip()
        if t:
            keys.add(term_key(t))
    return keys


def tracked_files(root: Path, globs: Sequence[str]) -> List[Path]:
    res = subprocess.run(
        ["git", "ls-files", "-z", "--", *globs], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if res.returncode == 0:
        return [
            (root / raw.decode("utf-8", "replace")).resolve()
            for raw in res.stdout.split(b"\0") if raw
        ]
    return [p.resolve() for g in globs for p in root.rglob(g) if p.is_file()]


def truthy(value: str) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def main() -> int:
    env = os.environ.get
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--globs", default=env("TERM_LINKS_GLOBS", DEFAULT_GLOBS))
    ap.add_argument("--paths-ignore", default=env("TERM_LINKS_PATHS_IGNORE", DEFAULT_PATHS_IGNORE))
    ap.add_argument("--terms-file", default=env("TERM_LINKS_TERMS_FILE", ""))
    ap.add_argument("--allow-file", default=env("TERM_LINKS_ALLOW_FILE", ""))
    ap.add_argument("--base-ref", default=env("TERM_LINKS_BASE_REF", ""))
    ap.add_argument("--diff", default=env("TERM_LINKS_DIFF_FILE", ""))
    ap.add_argument("--whole-tree", default=env("TERM_LINKS_WHOLE_TREE", "false"))
    ap.add_argument("--fail", default=env("TERM_LINKS_FAIL", "true"))
    args = ap.parse_args()

    root = Path.cwd()
    globs = args.globs.split()
    ignores = [glob_to_regex(p) for p in re.split(r"[,\n]+", args.paths_ignore) if p.strip()]
    should_fail = truthy(args.fail)

    files = [
        f for f in sorted(set(tracked_files(root, globs)))
        if not any(rx.match(str(f.relative_to(root)).replace("\\", "/")) for rx in ignores)
    ]

    added_map: Optional[Dict[Path, Set[int]]] = None
    if not truthy(args.whole_tree):
        if args.diff.strip() and Path(args.diff).is_file():
            added_map = parse_added_lines(
                Path(args.diff).read_text(encoding="utf-8", errors="replace"), root
            )
        elif args.base_ref.strip():
            added_map = diff_added_lines(args.base_ref.strip(), root, globs)
        if added_map is None:
            print(
                "::warning::check-term-links: no base-ref or diff to scope to (or git "
                "could not compute it); skipping rather than reflagging the whole tree. "
                "Pass whole-tree: true to scan everything.",
                file=sys.stderr,
            )
            return 0

    allowed_out = read_term_list(args.allow_file)
    contents: Dict[Path, List[str]] = {}
    terms: Dict[str, Set[str]] = {}
    for f in files:
        try:
            contents[f] = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            print(f"Warning: could not read {f}: {exc}", file=sys.stderr)
            continue
        masked, _ = preprocess(contents[f])
        if FILE_OPT_OUT_RE.search("\n".join(contents[f])):
            continue
        for k, ids in harvest_terms(masked, allowed_out).items():
            terms.setdefault(k, set()).update(ids)
    for k in read_term_list(args.terms_file):
        if usable_term(k, allowed_out):
            terms.setdefault(k, set())
    rx = term_regex(list(terms)) if terms else None

    findings: List[Finding] = []
    for f, lines in contents.items():
        added = added_map.get(f) if added_map is not None else None
        if added_map is not None and not added:
            continue
        findings.extend(scan_file(f, lines, terms, rx, added))

    severity = "error" if should_fail else "warning"
    if findings:
        print(f"check-term-links: {len(findings)} finding(s); {len(terms)} known term(s).\n")
        for fd in findings:
            rel = str(fd.file.relative_to(root)).replace("\\", "/")
            print(f"  {rel}:{fd.line}: [{fd.rule}] {fd.message}")
            print(f"::{severity} file={rel},line={fd.line},title=Term link::[{fd.rule}] {fd.message}")
    else:
        print(f"check-term-links: Clean ({len(terms)} known term(s), {len(files)} file(s)).")
    return 1 if findings and should_fail else 0


if __name__ == "__main__":
    sys.exit(main())
