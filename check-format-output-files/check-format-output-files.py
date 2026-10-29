#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a Quarto page that a per-format render would write over another format.

``quarto render --to FORMAT`` renders every page, even one whose front
matter does not list FORMAT, and names the output after the page. A page
with no ``revealjs`` entry therefore writes its deck to ``<stem>.html``,
replacing the notes page (mds ``linear-algebra.html``, 2026-10-28).

For each page with front matter, and each format in ``CFO_FORMATS``
(default ``revealjs pdf docx``), the page must:

- list the format under ``format:``; and
- give that entry an ``output-file`` (so it cannot reuse the HTML name).

A page with front matter but no ``format:`` key is flagged too. Pages whose
names start with ``_`` (subfiles) and ``_extensions/**`` are skipped.
``action.yml`` sets the ``CFO_*`` environment variables the script reads.
"""

import fnmatch
import os
import re
import subprocess
import sys
from typing import Dict, List, NamedTuple, Optional

DEFAULT_FORMATS = "revealjs pdf docx"
DEFAULT_IGNORE = "_extensions/**"


class Finding(NamedTuple):
    path: str
    line: Optional[int]
    message: str


def front_matter(lines: List[str]) -> Optional[List[str]]:
    """Return the YAML front matter lines, or None when there is none."""
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return lines[1:i]
    return None


def parse_formats(fm: List[str]) -> Optional[Dict[str, Dict]]:
    """Map each ``format:`` entry to {line, output_file}; None if no ``format:``."""
    start = None
    for i, raw in enumerate(fm):
        if re.match(r"^format\s*:", raw):
            start = i
            break
    if start is None:
        return None
    formats: Dict[str, Dict] = {}
    flow = re.match(r"^format\s*:\s*\{(.*)\}\s*$", fm[start])
    if flow:
        for name, body in re.findall(r"""["']?([\w-]+)["']?\s*:\s*(\{[^{}]*\}|[^,{}]*)""", flow.group(1)):
            formats[name] = {"line": start + 2, "output_file": "output-file" in body}
        return formats
    entry_indent = None
    current = None
    for i in range(start + 1, len(fm)):
        raw = fm[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0:
            break
        if entry_indent is None:
            entry_indent = indent
        if indent == entry_indent:
            name = re.match(r"""^\s*["']?([\w-]+)["']?\s*:(.*)$""", raw)
            if name:
                current = name.group(1)
                inline = re.search(r"\{[^}]*output-file\s*:\s*\S", name.group(2))
                formats[current] = {"line": i + 2, "output_file": bool(inline)}
        elif current and re.match(r"^\s*output-file\s*:\s*\S", raw):
            formats[current]["output_file"] = True
    return formats


def check_page(path: str, lines: List[str], required: List[str]) -> List[Finding]:
    fm = front_matter(lines)
    if fm is None:
        return []
    formats = parse_formats(fm)
    if formats is None:
        return [Finding(path, 1,
                        "no `format:` key, so `--to %s` writes `<page>.html` "
                        "over the notes page; list %s with an `output-file`"
                        % (required[0], ", ".join(required)))]
    findings = []
    for fmt in required:
        if fmt not in formats:
            findings.append(Finding(
                path, 1,
                "`format:` omits %s, but a per-format publish renders it "
                "anyway under the default name; add `%s:` with an `output-file:` key"
                % (fmt, fmt)))
        elif not formats[fmt]["output_file"]:
            findings.append(Finding(
                path, formats[fmt]["line"],
                "%s has no `output-file`, so it can overwrite the HTML page"
                % fmt))
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


def run(globs: List[str], patterns: List[str], required: List[str]) -> List[Finding]:
    findings = []
    for path in tracked_files(globs):
        if os.path.basename(path).startswith("_") or _ignored(path, patterns):
            continue
        if not path.endswith(".qmd") or not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            findings.extend(check_page(path, handle.read().splitlines(), required))
    return findings


def main() -> int:
    globs = os.environ.get("CFO_GLOBS", "").split() or ["*.qmd"]
    required = os.environ.get("CFO_FORMATS", "").split() or DEFAULT_FORMATS.split()
    ignore = os.environ.get("CFO_PATHS_IGNORE", "")
    patterns = [p.strip() for p in re.split(r"[,\n]", ignore) if p.strip()]
    patterns += DEFAULT_IGNORE.split()
    fail = os.environ.get("CFO_FAIL", "true").lower() != "false"
    findings = run(globs, patterns, required)
    level = "error" if fail else "warning"
    for f in findings:
        print("::%s file=%s,line=%d,title=Format output file::%s"
              % (level, f.path, f.line or 1, f.message))
    if not findings:
        print("check-format-output-files: every page names an output-file for %s"
              % ", ".join(required))
        return 0
    print("check-format-output-files: %d finding(s)" % len(findings))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
