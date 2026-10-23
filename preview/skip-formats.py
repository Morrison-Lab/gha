#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Leave slow formats out of a pull request's preview render.

PDF handouts and Word files dominate a large site's preview time. Quarto
cannot drop a declared format from a profile, and a page may declare the
format in its own front matter as well, so this edits the working copy before
the render: it removes the named `format:` entries from the project's
`_quarto*.yml` files and from the front matter of every `.qmd` page.

A format is kept when the pull request carries the label `preview:<format>`
(for example `preview:pdf`), and nothing is removed outside a preview. The
edit is textual, so comments and tags such as `!expr` survive; it understands
a `format:` mapping whose entries are indented consistently, which is how
Quarto projects write them.

Environment:
    SKIP_FORMATS     space-separated format names to leave out, e.g. "pdf docx"
    KEEP_FORMATS     space-separated names to keep regardless (for example docx
                     when tracked changes need the Word files)
    PR_LABELS        JSON array of the pull request's label names; each
                     `preview:<format>` keeps that format
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

LABEL_PREFIX = "preview:"
IGNORED_DIRS = {".git", ".quarto", "_freeze", "_site", "_book", "_manuscript", "node_modules", "renv"}
FORMAT_KEY = re.compile(r"^(?P<indent>[ \t]*)format:[ \t]*(?:#.*)?$")
INLINE_FORMAT = re.compile(r"^[ \t]*format:[ \t]*\S")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _is_blank_or_comment(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def strip_formats(text: str, names: set[str]) -> tuple[str, list[str]]:
    """Remove the `names` entries of every block `format:` mapping in `text`.

    Returns the new text and the names that were removed. A `format:` key left
    with no entries is removed too, since Quarto rejects an empty value.
    """
    lines = text.splitlines(keepends=True)
    removed: list[str] = []
    out: list[str] = []
    i = 0
    while i < len(lines):
        match = FORMAT_KEY.match(lines[i])
        if not match:
            out.append(lines[i])
            i += 1
            continue
        key_indent = len(match.group("indent"))
        # The block is the key line plus the lines after it that are blank,
        # comments, or indented deeper than the key.
        j = i + 1
        while j < len(lines) and (_is_blank_or_comment(lines[j]) or _indent(lines[j]) > key_indent):
            j += 1
        block = lines[i + 1 : j]
        child_indent = next(
            (_indent(b) for b in block if not _is_blank_or_comment(b)), None
        )
        if child_indent is None:
            out.append(lines[i])
            out.extend(block)
            i = j
            continue
        kept: list[str] = []
        k = 0
        entries = 0
        while k < len(block):
            line = block[k]
            entry = re.match(rf"^[ \t]{{{child_indent}}}([A-Za-z0-9_-]+):", line)
            if entry and _indent(line) == child_indent:
                # The entry owns the lines after it that are deeper, blank or comments.
                m = k + 1
                while m < len(block) and (
                    _is_blank_or_comment(block[m]) or _indent(block[m]) > child_indent
                ):
                    m += 1
                if entry.group(1) in names:
                    removed.append(entry.group(1))
                else:
                    kept.extend(block[k:m])
                    entries += 1
                k = m
            else:
                kept.append(line)
                k += 1
        if entries:
            out.append(lines[i])
            out.extend(kept)
        # else: drop the key line and everything under it
        i = j
    return "".join(out), removed


def split_front_matter(text: str) -> tuple[str, str]:
    """Return (front matter including fences, the rest); front matter is '' if absent."""
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text
    return text[: end + 5], text[end + 5 :]


def project_files(root: Path):
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and (
            path.suffix == ".qmd" or (path.name.startswith("_quarto") and path.suffix in {".yml", ".yaml"})
        ):
            yield path


def main() -> int:
    skip = set(os.environ.get("SKIP_FORMATS", "").split())
    keep = set(os.environ.get("KEEP_FORMATS", "").split())
    for label in json.loads(os.environ.get("PR_LABELS") or "[]"):
        if label.startswith(LABEL_PREFIX):
            keep.add(label[len(LABEL_PREFIX) :])
    names = skip - keep
    if not names:
        print("skip_formats: nothing to leave out")
        return 0
    root = Path(os.environ.get("PROJECT_PATH") or ".")
    changed: list[str] = []
    for path in project_files(root):
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".qmd":
            head, rest = split_front_matter(text)
            if not head:
                continue
            new_head, removed = strip_formats(head, names)
            new = new_head + rest
        else:
            new, removed = strip_formats(text, names)
        if not removed:
            continue
        st = path.stat()
        path.write_text(new, encoding="utf-8")
        os.utime(path, (st.st_atime, st.st_mtime))
        changed.append(str(path))
    listed = " and ".join(sorted(names))
    if not changed:
        print(f"skip_formats: found no {listed} format to remove")
        return 0
    print(f"skip_formats: removed {listed} from {len(changed)} files")
    # A one-line `format: pdf` or `format: [html, pdf]` is not handled; say so
    # instead of rendering the format silently.
    for path in project_files(root):
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".qmd":
            text = split_front_matter(text)[0]
        for line in text.splitlines():
            if INLINE_FORMAT.match(line) and any(re.search(rf"\b{n}\b", line) for n in names):
                print(
                    f"skip_formats: {path} still has an inline format entry: {line.strip()}",
                    file=sys.stderr,
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
