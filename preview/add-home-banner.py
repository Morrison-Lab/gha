#!/usr/bin/env python3
"""Add a banner to the preview home page naming the chapters this PR changed.

The cheapest possible consumer of `detect-changed-chapters.py`: it exists to
prove the substrate's output is usable before the intricate consumers (HTML
change highlighting, DOCX tracked changes) are built on it.

Ported from `ucdavis/win`'s `.github/scripts/add-home-banner.py`
(MIT, copyright 2025 d-morrison), with three changes:

  * Chapter titles are HTML-escaped. The original interpolated a heading
    straight into the banner, so a title containing `&` or `<` produced broken
    markup.
  * A missing home page, or a home page with no insertion point, is an error
    rather than a message on stderr that leaves the run green and the banner
    silently absent.
  * The list arrives as JSON in the environment rather than through a file
    written into the rendered site, and the skipped-comparison case says so
    instead of reading as "no changes".

Configuration (all via the environment, set by `preview/action.yml`):

  RENDERED_DIR       Directory holding this run's rendered site. Required.
  CHANGED_CHAPTERS   JSON array of changed chapter ids. Default `[]`.
  DETECTION_STATUS   `compared` or `skipped`. Default `compared`.
  SKIP_REASON        Why the comparison was skipped. Default ''.
  BANNER_INDEX       Home page, relative to RENDERED_DIR. Default `index.html`.
"""

import html
import json
import os
import re
import sys
from pathlib import Path

from _workflow_annotations import annotate

START_MARKER = "<!-- gha-preview-banner:start -->"
END_MARKER = "<!-- gha-preview-banner:end -->"

# Authored by this script at both ends, so there is never a nested occurrence to
# confuse the non-greedy match.
EXISTING_BANNER_RE = re.compile(
    re.escape(START_MARKER) + ".*?" + re.escape(END_MARKER), re.DOTALL
)

# Quarto's HTML template emits `<main class="content" id="quarto-document-content">`;
# `<body>` is the fallback for a template that does not.
ANCHOR_RES = (re.compile(r"<main[^>]*>", re.IGNORECASE), re.compile(r"<body[^>]*>", re.IGNORECASE))

HEADING_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL | re.IGNORECASE)
FALLBACK_HEADING_RE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


class BannerError(RuntimeError):
    """A condition that must stop the run rather than leave the banner absent."""


def chapter_href(rendered_dir, chapter_id):
    """The link target for a chapter id, or None when no rendered file matches."""
    direct = rendered_dir / f"{chapter_id}.html"
    if direct.is_file():
        return f"{chapter_id}.html"
    # Scanned rather than globbed: a chapter id is a file name, so a `[` or `*`
    # in it would otherwise be read as pattern syntax and match the wrong page.
    parent = (rendered_dir / chapter_id).parent
    stem = Path(chapter_id).name
    if parent.is_dir():
        matches = sorted(p for p in parent.iterdir() if p.is_file() and p.stem == stem)
        if matches:
            return matches[0].relative_to(rendered_dir).as_posix()
    return None


def chapter_title(rendered_dir, chapter_id, href):
    """The chapter's own first heading, falling back to its id."""
    if href is None:
        return chapter_id
    page = rendered_dir / href
    try:
        content = page.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return chapter_id
    match = HEADING_RE.search(content) or FALLBACK_HEADING_RE.search(content)
    if not match:
        return chapter_id
    title = html.unescape(TAG_RE.sub("", match.group(1))).strip()
    return title or chapter_id


def render_banner(rendered_dir, changed_chapters, status, skip_reason):
    if status == "skipped":
        body = (
            "<strong>Changes in this PR:</strong> not determined. "
            f"{html.escape(skip_reason)}"
        )
    elif not changed_chapters:
        body = (
            "<strong>Changes in this PR:</strong> no differences were found "
            "between this render and the published one."
        )
    else:
        links = []
        for chapter_id in changed_chapters:
            href = chapter_href(rendered_dir, chapter_id)
            label = html.escape(chapter_title(rendered_dir, chapter_id, href))
            if href is None:
                links.append(label)
            else:
                links.append(f'<a href="{html.escape(href, quote=True)}">{label}</a>')
        body = (
            "<strong>Changes in this PR:</strong> the following pages differ "
            f"from the published version: {', '.join(links)}"
        )

    return (
        f"{START_MARKER}\n"
        f'<div class="preview-home-changes-banner"><p>{body}</p></div>\n'
        f"{END_MARKER}\n"
    )


def apply_banner(index_path, banner):
    original = index_path.read_text(encoding="utf-8")

    # Replace rather than stack, so a re-run of the composite on the same
    # rendered tree does not accumulate banners.
    if EXISTING_BANNER_RE.search(original):
        index_path.write_text(
            EXISTING_BANNER_RE.sub(lambda _: banner.rstrip("\n"), original, count=1),
            encoding="utf-8",
        )
        return "replaced"

    for anchor in ANCHOR_RES:
        match = anchor.search(original)
        if match:
            index_path.write_text(
                original[: match.end()] + "\n" + banner + original[match.end() :],
                encoding="utf-8",
            )
            return "inserted"

    raise BannerError(
        f"{index_path} has no <main> or <body> element to insert the banner after"
    )


def main():
    rendered_dir_raw = os.getenv("RENDERED_DIR", "").strip()
    if not rendered_dir_raw:
        raise BannerError("RENDERED_DIR is required")
    rendered_dir = Path(rendered_dir_raw)
    if not rendered_dir.is_dir():
        raise BannerError(f"rendered directory {rendered_dir} does not exist")

    index_path = rendered_dir / (os.getenv("BANNER_INDEX", "").strip() or "index.html")
    if not index_path.is_file():
        raise BannerError(
            f"home page {index_path} does not exist; set `banner-index` if this "
            "project's preview home page is named something else"
        )

    raw = os.getenv("CHANGED_CHAPTERS", "").strip() or "[]"
    try:
        changed_chapters = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BannerError(f"CHANGED_CHAPTERS is not valid JSON: {exc}") from exc
    if not isinstance(changed_chapters, list):
        raise BannerError("CHANGED_CHAPTERS must be a JSON array")

    status = os.getenv("DETECTION_STATUS", "").strip() or "compared"
    if status not in {"compared", "skipped"}:
        raise BannerError(f"DETECTION_STATUS must be 'compared' or 'skipped', got {status!r}")

    banner = render_banner(rendered_dir, changed_chapters, status, os.getenv("SKIP_REASON", ""))
    action = apply_banner(index_path, banner)
    print(f"Banner {action} in {index_path} ({len(changed_chapters)} changed page(s)).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BannerError as error:
        print(annotate("error", error), file=sys.stderr)
        sys.exit(1)
