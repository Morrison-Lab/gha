#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a Quarto site whose search opens on Ctrl/Cmd-F or Ctrl/Cmd-S.

Quarto's ``website.search.keyboard-shortcut`` (``book.search.keyboard-shortcut``
for a book) defaults to ``["f", "/", "s"]``. Its script listens for ``keyup``
and never checks a modifier key, so the keyup that follows Ctrl/Cmd-F (find in
page) or Ctrl/Cmd-S (save) opens site search too (Ezra, 2026-10-28;
Morrison-Lab/gha#1287). Every Quarto site keeps only ``"/"``::

    website:
      search:
        keyboard-shortcut: ["/"]

A project directory is flagged when:

- it defines a site (a ``website:`` or ``book:`` key in a ``_quarto*.yml``
  file) and no ``_quarto*.yml`` file in the directory sets
  ``keyboard-shortcut`` (so the default applies), unless search is turned off
  with ``search: false``; or
- any ``keyboard-shortcut`` in the directory lists something other than
  exactly ``"/"``.

The files are small, so the check always reads them whole; there is no diff
scope. The parser is line-based so the action needs no YAML package: it reads
an inline list (``["/"]``) or a block list (``- "/"``) after the key.

Configuration (environment variables, set by the composite action):
  CSS_GLOBS          Space-separated git pathspecs (default: '_quarto*.yml').
  CSS_PATHS_IGNORE   Comma/newline-separated glob patterns to skip.
  CSS_FAIL           "false" => warn only; default "true".
"""

import fnmatch
import os
import re
import subprocess
import sys
from collections import defaultdict
from typing import Dict, List, NamedTuple, Optional

DEFAULT_GLOBS = "_quarto*.yml */_quarto*.yml"
DEFAULT_IGNORE = "_extensions/**"
ALLOWED = ["/"]

_SITE_RE = re.compile(r"^(website|book)\s*:")
_SEARCH_OFF_RE = re.compile(r"^(\s+)search\s*:\s*(false|no)\s*(#.*)?$", re.I)
_TOP_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:")
_SHORTCUT_RE = re.compile(r"^(\s*)keyboard-shortcut\s*:\s*(.*)$")


class Finding(NamedTuple):
    directory: str
    path: Optional[str]
    line: Optional[int]
    message: str


def _strip_comment(text: str) -> str:
    """Drop a trailing YAML comment that sits outside quotes."""
    quote = None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1].isspace()):
            return text[:i]
    return text


def _unquote(item: str) -> str:
    item = item.strip()
    if len(item) >= 2 and item[0] == item[-1] and item[0] in "\"'":
        return item[1:-1]
    return item


def parse_shortcuts(lines: List[str]) -> List[Dict]:
    """Return each ``keyboard-shortcut`` key as {line, values}."""
    found = []
    for i, raw in enumerate(lines):
        match = _SHORTCUT_RE.match(raw)
        if not match:
            continue
        indent = len(match.group(1))
        rest = _strip_comment(match.group(2)).strip()
        values: List[str] = []
        if rest.startswith("["):
            inner = rest[1:rest.rfind("]")] if "]" in rest else rest[1:]
            values = [_unquote(p) for p in inner.split(",") if p.strip()]
        elif rest:
            values = [_unquote(rest)]
        else:
            for nxt in lines[i + 1:]:
                body = _strip_comment(nxt).rstrip()
                if not body.strip():
                    continue
                item = re.match(r"^(\s*)-\s+(.*)$", body)
                if not item or len(item.group(1)) < indent:
                    break
                values.append(_unquote(item.group(2)))
        found.append({"line": i + 1, "values": values})
    return found


def search_turned_off(lines: List[str]) -> bool:
    """True when ``search: false`` is a direct child of ``website:``/``book:``.

    A deeper ``search: false`` (a sidebar's, for example) leaves the
    site-wide search, and its shortcut, on.
    """
    top = None
    child_indent = None
    for raw in lines:
        top_match = _TOP_RE.match(raw)
        if top_match:
            top = top_match.group(1)
            child_indent = None
            continue
        if top not in ("website", "book") or not raw.strip():
            continue
        if raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if child_indent is None:
            child_indent = indent
        match = _SEARCH_OFF_RE.match(raw)
        if match and indent == child_indent:
            return True
    return False


def check_project(directory: str, files: Dict[str, List[str]]) -> List[Finding]:
    """Check the ``_quarto*.yml`` files of one project directory."""
    is_site = False
    search_off = False
    shortcuts = []
    for path, lines in files.items():
        for raw in lines:
            if _SITE_RE.match(raw):
                is_site = True
        if search_turned_off(lines):
            search_off = True
        for found in parse_shortcuts(lines):
            shortcuts.append((path, found))
    findings = []
    for path, found in shortcuts:
        if found["values"] != ALLOWED:
            findings.append(Finding(
                directory, path, found["line"],
                "keyboard-shortcut is %s; keep only [\"/\"] so Ctrl/Cmd-F "
                "and Ctrl/Cmd-S do not open site search"
                % (found["values"] or "empty")))
    if is_site and not shortcuts and not search_off:
        findings.append(Finding(
            directory, None, None,
            "no keyboard-shortcut is set, so Quarto's default [\"f\", \"/\", "
            "\"s\"] applies and Ctrl/Cmd-F and Ctrl/Cmd-S open site search; "
            "add `search: {keyboard-shortcut: [\"/\"]}` under website: "
            "(or book:)"))
    return findings


def _ignored(path: str, patterns: List[str]) -> bool:
    for pat in patterns:
        regex = re.escape(pat).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
        regex = regex.replace(r"\?", "[^/]")
        if re.fullmatch(regex, path) or fnmatch.fnmatch(path, pat):
            return True
    return False


def tracked_files(globs: List[str]) -> List[str]:
    out = subprocess.run(["git", "ls-files", "--"] + globs, check=True,
                         capture_output=True, text=True).stdout
    return [p for p in out.splitlines() if p]


def run(globs: List[str], patterns: List[str]) -> List[Finding]:
    by_dir: Dict[str, Dict[str, List[str]]] = defaultdict(dict)
    for path in tracked_files(globs):
        if _ignored(path, patterns) or not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            by_dir[os.path.dirname(path) or "."][path] = handle.read().splitlines()
    findings = []
    for directory in sorted(by_dir):
        findings.extend(check_project(directory, by_dir[directory]))
    return findings


def main() -> int:
    globs = os.environ.get("CSS_GLOBS", "").split() or DEFAULT_GLOBS.split()
    ignore = os.environ.get("CSS_PATHS_IGNORE", "")
    patterns = [p.strip() for p in re.split(r"[,\n]", ignore) if p.strip()]
    patterns += DEFAULT_IGNORE.split()
    fail = os.environ.get("CSS_FAIL", "true").lower() != "false"
    findings = run(globs, patterns)
    level = "error" if fail else "warning"
    for f in findings:
        where = ""
        if f.path:
            where = "file=%s," % f.path
            if f.line:
                where += "line=%d," % f.line
        print("::%s %stitle=Site search shortcut::%s: %s"
              % (level, where, f.directory, f.message))
    if not findings:
        print("check-search-shortcut: no site opens search on f or s")
        return 0
    print("check-search-shortcut: %d finding(s)" % len(findings))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
