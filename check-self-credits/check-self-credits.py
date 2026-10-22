#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a formal credit to the group's own work.

The lab's rule (Ezra, 2026-10-16; gha#1076): a link to another of our sites is
fine, but we do not formally acknowledge content borrowed from ourselves the
way we acknowledge content adapted from others. Credit people outside the
group by name, keep ordinary citation of the group's published papers and
software, and link to the group's sites for further reading.

What is flagged, in ``.qmd``/``.md`` files, on a line a diff adds:

- **A citation of an own bibliography entry.** A ``.bib`` entry is own when its
  ``url``, ``doi``, ``howpublished`` or ``note`` contains one of the config's
  ``urls``, when its ``author`` or ``editor`` contains one of ``authors``, or
  when its key is in ``keys``. A key in ``allow-keys`` is never flagged (the
  group's published paper or software, cited as the original publication or as
  a tool used). A cited key is a bracketed ``[@key]`` or a bare ``@key``.
- **A credit phrase beside an own site or name.** A credit phrase is
  "adapted from", "borrowed from", "reproduced from", "reprinted from", "with
  permission from", "courtesy of" or "credit to", or a ``Source:`` line, or a
  div titled ``Source``. An own site or name is any entry of the config's
  ``urls`` or ``names``. It must sit in the same sentence as the phrase, on the
  same ``Source:`` line, or anywhere inside the ``Source`` div.

What is not flagged: a link or a mention on its own ("for further reading, see
the sds notes"), a citation of an entry that is not own, front matter, inline
code, code fences and chunk options.

Configuration file (``RC_CONFIG``, default ``.github/own-works.yml``), a
restricted YAML of top-level lists, each as ``key:`` followed by ``- item``
lines or as an inline ``[a, b]``::

    urls:        # substrings of a URL, DOI or note that mark a bib entry as own
      - morrison-lab.github.io
      - ucd-serg.github.io/lab-manual
    names:       # words or phrases that name an own site or work in prose
      - Morrison-Lab/sds
      - UCD-SERG lab manual
    authors:     # substrings of a bib author or editor that mark an entry as own
      - Morrison, Ezra
    keys:        # bib keys that are own whatever their fields say
    allow-keys:  # bib keys never flagged (published paper or software)
    allow-patterns:  # regexes; a matching line is never flagged
    bib-globs:   # git pathspecs of the .bib files (default: '*.bib')

Design notes, in the model of ``check-redundant-citations``:

- **Diff-scoped by default.** A finding is reported only when its line was
  *added* since ``RC_BASE_REF``. An added line whose exact text was also
  deleted in the same diff counts as moved, not new.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning; ``RC_WHOLE_TREE=true`` asks for
  the whole tree explicitly. With no config file it also skips: the lists of
  own works belong to the consumer.
- **Warn-only by default** (``RC_FAIL`` defaults to false).
- **The search space is reported**: files, lines, bib entries and own entries.

Environment variables (set by the composite action):
  RC_BASE_REF      Git ref/SHA to diff against.
  RC_CONFIG        Path of the config file.
  RC_GLOBS         Space-separated git pathspecs (default: '*.qmd *.md').
  RC_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  RC_FAIL          "true" => exit 1 on a finding.
  RC_WHOLE_TREE    "true" => scan every tracked matching file in full.
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

DEFAULT_GLOBS = "*.qmd *.md"
DEFAULT_CONFIG = ".github/own-works.yml"
DEFAULT_BIB_GLOBS = "*.bib"
_DEFAULT_FAIL = False

ADVICE = (
    "do not formally credit the group's own work; link to it for further "
    "reading, cite the original publication and a textbook for a result, and "
    "credit people outside the group by name"
)

XREF_PREFIXES = (
    "def-", "thm-", "lem-", "prp-", "cor-", "exm-", "exr-", "rem-", "eq-",
    "fig-", "tbl-", "sec-", "sol-", "lst-", "nte-", "tip-", "wrn-", "imp-",
    "cau-",
)

# -- Configuration -----------------------------------------------------------

LIST_KEYS = ("urls", "names", "authors", "keys", "allow-keys",
             "allow-patterns", "bib-globs")


class Config(NamedTuple):
    urls: List[str]
    names: List[str]
    authors: List[str]
    keys: Set[str]
    allow_keys: Set[str]
    allow_patterns: List["re.Pattern[str]"]
    bib_globs: List[str]


def _unquote(item: str) -> str:
    item = item.strip()
    if len(item) >= 2 and item[0] == item[-1] and item[0] in "\"'":
        return item[1:-1]
    return "" if item in ("~", "null", "Null", "NULL") else item


def parse_lists(text: str) -> Dict[str, List[str]]:
    """Top-level ``key:`` lists of a restricted YAML (block or inline form)."""
    out: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for raw in text.splitlines():
        line = re.sub(r"(^|\s)#.*$", "", raw).rstrip()
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            current = m.group(1)
            rest = m.group(2).strip()
            out.setdefault(current, [])
            if rest.startswith("[") and rest.endswith("]"):
                out[current] += [_unquote(p) for p in rest[1:-1].split(",")
                                 if p.strip()]
            elif rest:
                out[current].append(_unquote(rest))
            continue
        item = re.match(r"^\s*-\s+(.*)$", line)
        if item and current is not None:
            out[current].append(_unquote(item.group(1)))
    return out


def load_config(path: str) -> Optional[Config]:
    try:
        with open(path, encoding="utf-8-sig") as handle:
            lists = parse_lists(handle.read())
    except OSError:
        return None
    for key in lists:
        if key not in LIST_KEYS:
            print(f"::warning file={path}::Unknown key '{key}' in the "
                  f"own-works config; known keys are {', '.join(LIST_KEYS)}.")
    patterns = []
    for pat in lists.get("allow-patterns", []):
        try:
            patterns.append(re.compile(pat))
        except re.error:
            print(f"::warning file={path}::Ignoring invalid allow-pattern "
                  f"'{pat}'.")
    return Config(
        urls=[u.lower() for u in lists.get("urls", []) if u],
        names=[n for n in lists.get("names", []) if n],
        authors=[a.lower() for a in lists.get("authors", []) if a],
        keys=set(lists.get("keys", [])),
        allow_keys=set(lists.get("allow-keys", [])),
        allow_patterns=patterns,
        bib_globs=lists.get("bib-globs") or DEFAULT_BIB_GLOBS.split(),
    )


# -- Bibliography ------------------------------------------------------------

ENTRY_RE = re.compile(r"@([A-Za-z]+)\s*\{\s*([^,\s{}]+)\s*,")
SKIP_RE = re.compile(r"@(?:comment|string|preamble)\s*\{", re.IGNORECASE)
FIELD_RE = re.compile(r"([A-Za-z][\w-]*)\s*=\s*")


def _balanced(text: str, start: int) -> Tuple[str, int]:
    """Value starting at ``text[start]`` (braced, quoted or bare) and its end."""
    if start >= len(text):
        return "", start
    if text[start] == "{":
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start + 1:i], i + 1
        return text[start + 1:], len(text)
    if text[start] == '"':
        i = start + 1
        while i < len(text) and text[i] != '"':
            i += 2 if text[i] == "\\" else 1
        return text[start + 1:i], min(i + 1, len(text))
    m = re.match(r"[^,\n}]*", text[start:])
    return (m.group(0).strip() if m else ""), start + (m.end() if m else 0)


def parse_bib(text: str) -> Dict[str, Dict[str, str]]:
    """``{key: {field: value}}`` for each entry of a BibTeX file."""
    entries: Dict[str, Dict[str, str]] = {}
    text = re.sub(r"(?m)^[ \t]*%.*$", "", text)  # BibTeX comment lines
    pos = 0
    while True:
        m = ENTRY_RE.search(text, pos)
        skip = SKIP_RE.search(text, pos)
        if skip and (m is None or skip.start() < m.start()):
            pos = max(_balanced(text, skip.end() - 1)[1], skip.end())
            continue
        if not m:
            break
        opening = text.index("{", m.start())
        inner, end = _balanced(text, opening)
        pos = max(end, m.end())
        if m.group(1).lower() in ("comment", "string", "preamble"):
            continue
        body = text[m.end():max(end - 1, m.end())]
        fields: Dict[str, str] = {}
        i = 0
        while i < len(body):
            f = FIELD_RE.search(body, i)
            if not f:
                break
            value, stop = _balanced(body, f.end())
            fields[f.group(1).lower()] = " ".join(value.split())
            i = max(stop, f.end())
        entries[m.group(2)] = fields
    return entries


def own_keys(entries: Dict[str, Dict[str, str]], cfg: Config) -> Set[str]:
    """Keys of the entries that are the group's own work, minus the allowed."""
    own: Set[str] = set()
    for key, fields in entries.items():
        where = " ".join(fields.get(n, "") for n in
                         ("url", "doi", "howpublished", "note")).lower()
        who = " ".join(fields.get(n, "") for n in ("author", "editor")).lower()
        if (key in cfg.keys
                or any(u in where for u in cfg.urls)
                or any(a in who for a in cfg.authors)):
            own.add(key)
    return own - cfg.allow_keys


# -- Scanning ----------------------------------------------------------------

FENCE_RE = re.compile(r"^[ \t>]*(`{3,}|~{3,})(.*)$")
DIV_OPEN_RE = re.compile(r"^\s{0,3}(:{3,})\s*(\S.*)?$")
CITE_RE = re.compile(r"(?<![\w/#=&?.\-])@([A-Za-z_][\w:.\-]*\w|[A-Za-z_])")
CREDIT_RE = re.compile(
    r"\b(?:adapted|borrowed|reproduced|reprinted)\s+(?:\w+\s+)?from\b|"
    r"\bwith\s+permission\s+from\b|\bcourtesy\s+of\b|"
    r"\bcredit(?:s|ed)?\s+(?:to|goes)\b",
    re.IGNORECASE,
)
SOURCE_LINE_RE = re.compile(
    r"^\s*(?:>\s*)?(?:[-*+]\s+)?[*_]*Source[*_]*:", re.IGNORECASE)
SOURCE_DIV_RE = re.compile(
    r"^\s*Source\s*$|\.source(?![\w-])|title\s*=\s*(?:\"Source\"|'Source')",
    re.IGNORECASE)
ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])[ \t]+")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
SENTENCE_END_RE = re.compile(r"(?<=[.!?])[)\]\"'*_]*\s+(?=\S)")
ABBREVIATION_RE = re.compile(
    r"(?:\b[A-Z]|\b(?:al|Dr|Prof|Mr|Mrs|Ms|vs|etc|cf|Fig|Eq|No|Vol|pp?)"
    r"|\be\.g|\bi\.e)\.$")


def sentence_spans(text: str) -> List[Tuple[int, int]]:
    """``(start, end)`` of each sentence, not splitting at an abbreviation."""
    spans, prev = [], 0
    for sep in SENTENCE_END_RE.finditer(text):
        before = text[prev:sep.start()]
        if ABBREVIATION_RE.search(before.rstrip(")]\"'*_")):
            continue
        spans.append((prev, sep.start()))
        prev = sep.end()
    spans.append((prev, len(text)))
    return spans


class Finding(NamedTuple):
    line: int
    kind: str      # "citation" or "credit"
    detail: str


def _name_regexes(cfg: Config) -> List["re.Pattern[str]"]:
    out = []
    for name in cfg.names:
        body = re.escape(name).replace(r"\ ", r"\s+")
        out.append(re.compile(r"(?<![\w/])" + body + r"(?![\w])",
                              re.IGNORECASE))
    for url in cfg.urls:
        out.append(re.compile(re.escape(url), re.IGNORECASE))
    return out


def _own_mention(text: str, names: List["re.Pattern[str]"]) -> Optional[str]:
    for rx in names:
        m = rx.search(text)
        if m:
            return m.group(0)
    return None


def scan_file(lines: List[str], cfg: Config, own: Set[str]
              ) -> Tuple[List[Finding], int]:
    """Findings in one file and the number of paragraphs examined."""
    names = _name_regexes(cfg)
    findings: List[Finding] = []
    fence: Optional[Tuple[str, int]] = None
    # Paragraph = consecutive prose lines; a Source div is its own context.
    para: List[Tuple[int, str]] = []
    divs: List[Tuple[int, bool]] = []  # (colon count, is Source div)
    examined = 0

    def flush() -> None:
        nonlocal examined
        if not para:
            return
        examined += 1
        in_source = any(is_src for _c, is_src in divs)
        text = "\n".join(t for _n, t in para)
        starts, pos = [], 0
        for _n, t in para:
            starts.append(pos)
            pos += len(t) + 1

        def line_at(offset: int) -> int:
            idx = 0
            for k, st in enumerate(starts):
                if st <= offset:
                    idx = k
            return para[idx][0]

        if in_source:
            spans = [(0, len(text))]
        else:
            spans = sentence_spans(text)
        reported = set()
        for a, b in spans:
            sentence = text[a:b]
            phrase = None if in_source else CREDIT_RE.search(sentence)
            if not (in_source or phrase):
                continue
            hits = [h for rx in names for h in rx.finditer(sentence)]
            own_hit = hits[0].group(0) if hits else ""
            if hits and phrase:
                # Report the phrase's line too, so a newly added credit
                # phrase beside an unchanged own-site line is still seen.
                hits.append(phrase)
            for hit in sorted(hits, key=lambda h: h.start()):
                ln = line_at(a + hit.start())
                if ln not in reported:
                    reported.add(ln)
                    findings.append(Finding(
                        ln, "credit",
                        f"credits the group's own work ('{own_hit}')"))
        for n, t in para:
            if SOURCE_LINE_RE.match(t) and n not in reported:
                mention = _own_mention(t, names)
                if mention:
                    reported.add(n)
                    findings.append(Finding(
                        n, "credit",
                        f"credits the group's own work ('{mention}')"))
        para.clear()

    front = bool(lines) and lines[0].strip() == "---"
    for idx, raw in enumerate(lines):
        n = idx + 1
        if front:
            if idx > 0 and raw.strip() in ("---", "..."):
                front = False
            continue
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m:
            flush()
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        d = DIV_OPEN_RE.match(raw)
        if d:
            flush()
            colons, header = len(d.group(1)), d.group(2) or ""
            if header:
                divs.append((colons, bool(SOURCE_DIV_RE.search(header))))
            elif divs:
                same = [i for i, (c, _s) in enumerate(divs) if c == colons]
                divs.pop(same[-1] if same else -1)
            continue
        if raw.lstrip().startswith("#|"):
            continue
        if not raw.strip() or HEADING_RE.match(raw):
            flush()
            continue
        if any(rx.search(raw) for rx in cfg.allow_patterns):
            continue
        if ITEM_RE.match(raw):
            flush()
        raw = INLINE_CODE_RE.sub(lambda mm: " " * len(mm.group(0)), raw)
        for c in CITE_RE.finditer(raw):
            key = c.group(1)
            if key.startswith(XREF_PREFIXES) or key not in own:
                continue
            findings.append(Finding(n, "citation",
                                    f"cites @{key}, an entry for the "
                                    f"group's own work"))
        para.append((n, raw))
    flush()
    return findings, examined


def format_message(f: Finding) -> str:
    return f"This line {f.detail}. Fix: {ADVICE}"


# -- Git plumbing ------------------------------------------------------------

def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff: str) -> Tuple[Dict[str, Dict[int, str]], Set[str]]:
    """Added ``{path: {line_number: text}}`` and the set of deleted texts."""
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
            path = (None if target == "/dev/null"
                    else target[2:] if target.startswith("b/") else target)
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


def _split_list(value: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,\n]", value) if p.strip()]


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def _read_lines(path: str) -> Optional[List[str]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return None
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def load_own_keys(cfg: Config) -> Tuple[Set[str], int]:
    """Own bib keys across every tracked ``.bib`` file and the entry count."""
    out = _run_git(["ls-files", "--", *cfg.bib_globs]) or ""
    entries: Dict[str, Dict[str, str]] = {}
    for rel in out.splitlines():
        try:
            with open(rel, encoding="utf-8", errors="replace") as handle:
                entries.update(parse_bib(handle.read()))
        except OSError:
            continue
    return own_keys(entries, cfg), len(entries)


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    paragraphs: int
    entries: int
    own: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool, cfg: Config) -> Report:
    """Scan the added lines since ``base_ref``, or every line when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, 0, 0, 0, True)
        for rel in out.splitlines():
            if rel and not _ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, 0, 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, 0, 0, True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, 0, 0, 0, True)
        added, deleted = parse_diff(diff)
        for rel, numbered in added.items():
            if _ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if not (text.strip() and text in deleted)}

    own, entries = load_own_keys(cfg)
    findings: List[Tuple[str, Finding]] = []
    files = lines = paragraphs = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        found, examined = scan_file(content, cfg, own)
        paragraphs += examined
        for f in found:
            if keep is None or f.line in keep:
                findings.append((rel, f))
    return Report(findings, files, lines, paragraphs, entries, len(own), False)


def main() -> int:
    base_ref = os.environ.get("RC_BASE_REF", "").strip()
    globs = os.environ.get("RC_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("RC_PATHS_IGNORE", "")))
    fail = _env_flag("RC_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("RC_WHOLE_TREE", False)
    config_path = os.environ.get("RC_CONFIG", "").strip() or DEFAULT_CONFIG

    cfg = load_config(config_path)
    if cfg is None:
        print(f"::warning::Skipping the self-credits check: no config file "
              f"at '{config_path}'. List the group's own sites, names and "
              f"works there (see website/reference/check-self-credits.qmd in gha).")
        return 0

    report = run_check(base_ref, globs, ignores, whole_tree, cfg)
    if report.skipped:
        reason = (f"could not diff against '{base_ref}'" if base_ref
                  else "no base-ref given")
        # With no base-ref (a push run) the skip is expected, so it is not an annotation.
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the self-credits check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every credit the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.lines} line(s) across {report.files} file(s), "
          f"{report.paragraphs} paragraph(s); {report.own} of "
          f"{report.entries} bibliography entr(ies) are the group's own "
          f"(scope: {scope}).")
    if not report.findings:
        print("No added line credits the group's own work.")
        return 0

    severity = "error" if fail else "warning"
    for rel, f in report.findings:
        print(f"::{severity} file={rel},line={f.line}::{format_message(f)}")
    print(f"\n{len(report.findings)} credit(s) to the group's own work.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
