#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a definition whose bolded defined term is not linked to its Wiktionary entry.

The lab's rule (Ezra, 2026-11-06; Morrison-Lab/psw#505): in a ``#def-`` div,
the first bolded instance of each term being defined links to its entry in
Wiktionary, where an entry exists. The terms are the comma-separated names in
the div title. Math in a title is ignored.

A bolded instance is ``**term**``, ``**[term](url)**`` or ``[**term**](url)``.
A definition is flagged when

- its first bolded instance of a title name is not a link to
  ``en.wiktionary.org/wiki/``, and Wiktionary has an entry for that name, or
- it links a Wiktionary page that does not exist.

Wiktionary page titles are case-sensitive, so the lower-cased name is tried
first and then the name as written. Multiword technical terms and symbols
usually have no entry and are then not flagged. A network failure never fails
the run: the definition is skipped with a warning.

Diff-scoped: a definition is examined when the diff adds a line inside it.
``DWK_WHOLE_TREE=true`` scans every tracked matching file.
``<!-- wiktionary-link: allow -->`` inside a definition exempts it.

Configuration (environment variables, set by the composite action):
  DWK_BASE_REF    Git ref/SHA to diff against. Empty and not whole-tree => skip.
  DWK_GLOBS       Space-separated git pathspecs (default: '*.qmd').
  DWK_FAIL        "true" => exit 1 on a finding; default "false" => warnings.
  DWK_WHOLE_TREE  "true" => scan every tracked matching file in full.
  DWK_OFFLINE     "true" => skip the lookups (used by tests and offline runs).
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

DEFAULT_GLOBS = "*.qmd"
API = "https://en.wiktionary.org/w/api.php"
WIKI_PREFIX = "https://en.wiktionary.org/wiki/"

DEF_OPEN_RE = re.compile(r"^ {0,3}:{3,}\s*\{[^}]*#def-[^}]*\}")
FENCE_LINE_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
TITLE_ATTR_RE = re.compile(r"""title\s*=\s*(?:"([^"]*)"|'([^']*)')""")
MATH_RE = re.compile(r"\$[^$]*\$")
ALLOW_RE = re.compile(r"<!--\s*wiktionary-link\s*:\s*allow\b", re.IGNORECASE)
# Group 1/2: link around bold text; 3/4: bold text containing an optional link.
BOLD_RE = re.compile(r"\[\*\*(.+?)\*\*\]\(([^)\s]*)\)|\*\*(.+?)\*\*")
INNER_LINK_RE = re.compile(r"^\[(.+?)\]\(([^)\s]*)\)$")
WIKT_LINK_RE = re.compile(r"\]\((https://en\.wiktionary\.org/wiki/[^)\s]+)\)")

Lookup = Callable[[str], Optional[bool]]


def title_names(title: str) -> List[str]:
    plain = MATH_RE.sub("", title)
    return [n.strip() for n in plain.split(",") if n.strip()]


def def_blocks(lines: List[str]) -> List[Tuple[int, int, str, str]]:
    """``(start, end, title, body)`` per outermost ``#def-`` div; 1-based line numbers."""
    blocks = []
    depth, start = 0, None
    for idx, raw in enumerate(lines):
        m = FENCE_LINE_RE.match(raw)
        if not m:
            continue
        if m.group(2):
            if depth == 0 and DEF_OPEN_RE.match(raw):
                start = idx
            depth += 1
        elif depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                inner = lines[start + 1:idx]
                title = ""
                attr = TITLE_ATTR_RE.search(lines[start])
                if attr:
                    title = attr.group(1) or attr.group(2)
                else:
                    for text in inner:
                        if text.strip():
                            h = HEADING_RE.match(text)
                            title = h.group(1) if h else ""
                            break
                blocks.append((start + 1, idx + 1, title, "\n".join(inner)))
                start = None
    return blocks


def bold_instances(body: str) -> List[Tuple[str, Optional[str]]]:
    """``(plain text, link target or None)`` of each bolded span, in order."""
    found = []
    for m in BOLD_RE.finditer(body):
        if m.group(1) is not None:
            found.append((m.group(1).strip(), m.group(2)))
        else:
            text = m.group(3).strip()
            inner = INNER_LINK_RE.match(text)
            found.append((inner.group(1), inner.group(2)) if inner else (text, None))
    return found


def candidates(name: str) -> List[str]:
    lower = name.lower()
    return [lower] if lower == name else [lower, name]


def entry_for(name: str, lookup: Lookup) -> Optional[str]:
    """The Wiktionary page title for ``name``, or None; raises on lookup failure."""
    for cand in candidates(name):
        result = lookup(cand)
        if result is None:
            raise RuntimeError("lookup unavailable")
        if result:
            return cand
    return None


def api_lookup(title: str) -> Optional[bool]:
    """True/False for whether Wiktionary has the page; None on a network error."""
    url = f"{API}?action=query&format=json&titles={urllib.parse.quote(title)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Morrison-Lab-gha-check-def-wiktionary/1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    pages = data.get("query", {}).get("pages", {})
    return bool(pages) and not any("missing" in p or "invalid" in p for p in pages.values())


def wiktionary_title(url: str) -> str:
    return urllib.parse.unquote(url[len(WIKI_PREFIX):].split("#")[0]).replace("_", " ")


def check_block(title: str, body: str, lookup: Lookup) -> List[str]:
    """Messages for one definition; empty when it follows the rule."""
    if ALLOW_RE.search(body):
        return []
    messages: List[str] = []
    bolds = bold_instances(body)
    for name in title_names(title):
        first = next(((t, u) for t, u in bolds if t.lower() == name.lower()), None)
        if first is None:
            continue
        linked = bool(first[1] and first[1].startswith(WIKI_PREFIX))
        if linked:
            continue
        try:
            page = entry_for(name, lookup)
        except RuntimeError:
            messages.append(f"::NOTE::could not reach Wiktionary to look up '{name}'; skipped.")
            continue
        if page:
            messages.append(
                f"The first bolded '{name}' is not linked to its Wiktionary entry. "
                f"Fix: **[{name}]({WIKI_PREFIX}{urllib.parse.quote(page.replace(' ', '_'))})**, "
                f"or add <!-- wiktionary-link: allow --> if the entry is the wrong sense.")
    for url in WIKT_LINK_RE.findall(body):
        page = wiktionary_title(url)
        try:
            exists = lookup(page)
        except Exception:  # noqa: BLE001 - a lookup failure must not fail the run
            exists = None
        if exists is False:
            messages.append(f"The Wiktionary link {url} points to a page that does not exist.")
    return messages


def added_lines(diff: str) -> Dict[str, Set[int]]:
    """Added line numbers per path from ``git diff -U0`` output."""
    added, _deleted = diffscope.parse_diff(diff)
    return {path: set(numbered) for path, numbered in added.items()}


def wanted_lines(base_ref: str, globs: List[str], whole_tree: bool
                 ) -> Optional[Dict[str, Optional[Set[int]]]]:
    """Files to scan, each with its added lines (None = every line)."""
    if whole_tree:
        paths = diffscope.git_paths(["ls-files", "--", *globs])
        return None if paths is None else {p: None for p in paths}
    if not base_ref:
        return None
    base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
    if not base or not base.strip():
        return None
    diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                              base.strip(), "--", *globs])
    return None if diff is None else added_lines(diff)


def main() -> int:
    env = os.environ.get
    base_ref = env("DWK_BASE_REF", "").strip()
    globs = env("DWK_GLOBS", DEFAULT_GLOBS).split() or [DEFAULT_GLOBS]
    truthy = ("1", "true", "yes", "on")
    fail = env("DWK_FAIL", "").strip().lower() in truthy
    whole = env("DWK_WHOLE_TREE", "").strip().lower() in truthy
    offline = env("DWK_OFFLINE", "").strip().lower() in truthy
    wanted = wanted_lines(base_ref, globs, whole)
    if wanted is None or offline:
        print("Skipping the Wiktionary link check for this run "
              f"({'offline' if offline else 'no base to diff against'}).")
        return 0
    severity = "error" if fail else "warning"
    examined = findings = 0
    for rel in sorted(wanted):
        try:
            with open(rel, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().split("\n")
        except OSError:
            continue
        keep = wanted[rel]
        for start, end, title, body in def_blocks(lines):
            if keep is not None and not any(start <= n <= end for n in keep):
                continue
            examined += 1
            for msg in check_block(title, body, api_lookup):
                if msg.startswith("::NOTE::"):
                    print(f"::warning file={rel},line={start}::{msg[8:]}")
                    continue
                findings += 1
                print(f"::{severity} file={rel},line={start}::{msg}")
    print(f"Examined {examined} definition(s) in {len(wanted)} file(s); {findings} flagged.")
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
