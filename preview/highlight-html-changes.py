#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Highlight added and modified text in rendered HTML files compared to deployed branch.

Compares the PR's rendered HTML against the version published on `gh-pages` and
injects inline highlighting and a summary banner for changed sections, so
reviewers see what changed in the rendered output rather than in source diffs.

Ported from `ucdavis/win`'s `.github/scripts/highlight-html-changes.py`
(MIT, copyright 2025 d-morrison), and rewritten to Morrison-Lab/gha fail-fast bar:

  * Every git call is checked.
  * Distinguishes "page is new in PR" from "comparison failed/missing base".
  * Filters build metadata (htmlwidgets IDs, ISO timestamps, comments) so pages
    differing only in build metadata are NOT highlighted and remain byte-identical.
  * Preserves HTML tags and hierarchy without tag corruption.
  * Reads published files directly via git object lookup without materializing
    unneeded trees to disk.
  * Replaces elements strictly within main content scope, avoiding spurious edits
    in navigation, sidebars, or headers.

Configuration is read from the environment. `preview/action.yml` sets these:

  RENDERED_DIR         Directory holding this run's rendered site. Required.
  CHANGED_CHAPTERS     JSON array of changed chapter ids. Default `[]`.
  DETECTION_STATUS     `compared` or `skipped`. Default `compared`.
  SKIP_REASON          Why comparison was skipped; empty when compared.
  CHAPTER_GLOB         Glob selecting rendered files when CHANGED_CHAPTERS is unset.
                       Default `chapters/*.html`.
  DEPLOYED_BRANCH      Branch on the deployed remote. Default `gh-pages`.
  DEPLOYED_SUBDIR      Path prefix, within deployed branch, at which site root lives.
                       Default '' (the branch root).
  NORMALIZE_PATTERNS   Newline-separated regexes whose matches are blanked before
                       comparison, in addition to built-in defaults.
  MAX_ELEMENTS_FOR_PAIRWISE  Max candidate elements per page for pairwise
                             SequenceMatcher diffing. Default 500.

`preview/action.yml` does not set these, so under the action they always take
their defaults; they exist for running the script directly (tests, local runs).
The three budgets are internal safety nets, not action inputs:

  DEPLOYED_REMOTE      Git remote holding published site. Default `origin`.
  REPO_DIR             Git repository to run in. Default `.`.
  HIGHLIGHT_MAX_ELEMENT_CHARS  Elements with more text than this are left out
                             of the comparison (never highlighted). Default 20000.
  HIGHLIGHT_PAGE_BUDGET_SECONDS  Wall-clock budget for one page's pairwise
                             matching; a page that exceeds it is left
                             unhighlighted with a warning. Default 60.
  HIGHLIGHT_TOTAL_BUDGET_SECONDS  The same budget across all pages. Default 300.
"""

import difflib
import html
import json
import os
import re
import sys
import time
from pathlib import Path

from _preview_substrate import (
    DEFAULT_NORMALIZE_PATTERNS,
    PLACEHOLDER,
    TEXT_SUFFIXES,
    compile_patterns,
    normalize,
    published_paths,
    read_published,
    resolve_deployed_ref,
    run_git,
    GitError,
)
from _workflow_annotations import annotate

PAGE_BANNER_START = "<!-- gha-preview-page-banner:start -->"
PAGE_BANNER_END = "<!-- gha-preview-page-banner:end -->"

EXISTING_PAGE_BANNER_RE = re.compile(
    re.escape(PAGE_BANNER_START) + ".*?" + re.escape(PAGE_BANNER_END), re.DOTALL
)

ANCHOR_RES = (
    re.compile(r"<main[^>]*>", re.IGNORECASE),
    re.compile(r"<body[^>]*>", re.IGNORECASE),
)

COMPARABLE_ELEMENTS = "p|h[1-6]|li|blockquote"
ELEMENT_RE = re.compile(
    rf"(<(?:{COMPARABLE_ELEMENTS})[^>]*>.*?</(?:{COMPARABLE_ELEMENTS})>)",
    re.DOTALL | re.IGNORECASE,
)

TAG_RE = re.compile(r"<[^>]+>")

def _get_max_elements_for_pairwise():
    raw = os.environ.get("MAX_ELEMENTS_FOR_PAIRWISE", "500").strip()
    try:
        return int(raw) if raw else 500
    except ValueError:
        return 500


MAX_ELEMENTS_FOR_PAIRWISE = _get_max_elements_for_pairwise()


def _env_float(name, default):
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


# The element-count cap above does not bound per-element size, and
# SequenceMatcher.ratio() is quadratic in its inputs' length. ELEMENT_RE is
# non-greedy but tag-agnostic, so a match opening on a <p> before an
# htmlwidget runs across the widget's <script> JSON to the next closing tag:
# on Morrison-Lab/mds's algebra.html (plotly figures) one "element" carried
# 10 MB of text, and ratio() on that pair never finished. Such an element is
# not prose, and an over-length one is not something a reader scans for a
# changed word, so both are left out of the comparison (never highlighted)
# rather than compared on a truncated prefix or an approximate ratio, which
# would silently drop real highlights.
MAX_ELEMENT_TEXT_CHARS = int(_env_float("HIGHLIGHT_MAX_ELEMENT_CHARS", 20000))
# Last-resort wall-clock bounds, so no pathological page can consume the job.
PAGE_TIME_BUDGET_SECONDS = _env_float("HIGHLIGHT_PAGE_BUDGET_SECONDS", 60.0)
TOTAL_TIME_BUDGET_SECONDS = _env_float("HIGHLIGHT_TOTAL_BUDGET_SECONDS", 300.0)

NON_PROSE_RE = re.compile(r"<(?:script|style)\b", re.IGNORECASE)
SCRIPT_STYLE_BLOCK_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>", re.DOTALL | re.IGNORECASE
)


class BudgetExceeded(Exception):
    """A page's pairwise matching ran past its wall-clock budget."""


def _comparable(elem, text):
    return (
        bool(text)
        and len(text) <= MAX_ELEMENT_TEXT_CHARS
        and not NON_PROSE_RE.search(elem)
    )


# Aliased to GitError from substrate
HighlightError = GitError


def normalize_text(text, patterns):
    """Normalize text/HTML for comparison."""
    text = normalize(text, patterns)
    # Remove HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def locate_main_content(html_str):
    """Locate main content match span and inner content within full HTML.

    Returns (inner_content, start_inner_index, end_inner_index) or (html_str, 0, len(html_str)).
    """
    for pattern in (
        r"(<main[^>]*>)(.*?)(</main>)",
        r"(<div[^>]*id=[\x22\x27]quarto-document-content[\x22\x27][^>]*>)(.*?)(</div>)",
        r"(<div[^>]*class=[\x22\x27][^\x22\x27]*content[^\x22\x27]*[\x22\x27][^>]*>)(.*?)(</div>)",
        r"(<body[^>]*>)(.*?)(</body>)",
    ):
        match = re.search(pattern, html_str, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(2), match.start(2), match.end(2)
    return html_str, 0, len(html_str)


def extract_main_content(html_str):
    """Extract main content section from HTML, ignoring navigation and metadata."""
    inner, _, _ = locate_main_content(html_str)
    return inner


def extract_text_from_element(element_html):
    """Extract plain text from an HTML element."""
    text = TAG_RE.sub("", element_html)
    return html.unescape(text).strip()


def apply_highlights_to_text(text, text_start_pos, changed_ranges):
    """Apply highlight marks to a text segment based on changed ranges."""
    if not text:
        return text

    text_end_pos = text_start_pos + len(text)
    overlapping = []

    for start, end, change_type in changed_ranges:
        if start < text_end_pos and end > text_start_pos:
            overlap_start = max(0, start - text_start_pos)
            overlap_end = min(len(text), end - text_start_pos)
            if overlap_start < overlap_end:
                overlapping.append((overlap_start, overlap_end, change_type))

    if not overlapping:
        return text

    overlapping.sort()
    result = []
    last_end = 0

    for overlap_start, overlap_end, change_type in overlapping:
        if overlap_start > last_end:
            result.append(text[last_end:overlap_start])

        highlighted_text = text[overlap_start:overlap_end]
        if change_type == "replace":
            result.append(
                f'<mark class="preview-text-changed" style="background-color: #fff3cd; color: inherit; padding: 1px 2px; border-radius: 2px;">{highlighted_text}</mark>'
            )
        elif change_type == "insert":
            result.append(
                f'<mark class="preview-text-added" style="background-color: #d1e7dd; color: inherit; padding: 1px 2px; border-radius: 2px;">{highlighted_text}</mark>'
            )

        last_end = overlap_end

    if last_end < len(text):
        result.append(text[last_end:])

    return "".join(result)


def highlight_html_diff(old_html, new_html):
    """Highlight differences between old and new inner HTML content, preserving HTML tags."""
    old_tokens = re.findall(r"(<[^>]+>|[^<]+)", old_html)
    new_tokens = re.findall(r"(<[^>]+>|[^<]+)", new_html)

    old_text = "".join(t for t in old_tokens if not t.startswith("<"))
    new_text = "".join(t for t in new_tokens if not t.startswith("<"))

    if not old_text.strip() or not new_text.strip():
        return new_html

    old_words = re.findall(r"\S+|\s+", old_text)
    new_words = re.findall(r"\S+|\s+", new_text)

    matcher = difflib.SequenceMatcher(None, old_words, new_words)
    changed_ranges = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            start_pos = len("".join(new_words[:j1]))
            end_pos = len("".join(new_words[:j2]))
            changed_ranges.append((start_pos, end_pos, tag))

    if not changed_ranges:
        return new_html

    result = []
    text_pos = 0

    for token in new_tokens:
        if token.startswith("<"):
            result.append(token)
        else:
            token_len = len(token)
            token_end = text_pos + token_len
            highlighted = apply_highlights_to_text(token, text_pos, changed_ranges)
            result.append(highlighted)
            text_pos = token_end

    return "".join(result)


def highlight_changed_elements(old_html, new_html, patterns, deadline=None):
    """Find and highlight changed paragraphs and sections in the HTML.

    Returns (highlighted_html, changes_count, similarity_ratio). Raises
    BudgetExceeded when pairwise matching is still running at `deadline`
    (a time.monotonic() value; None means no limit).
    """
    old_content = extract_main_content(old_html)
    new_content, start_idx, end_idx = locate_main_content(new_html)

    norm_old = normalize_text(old_content, patterns)
    norm_new = normalize_text(new_content, patterns)

    if norm_old == norm_new:
        return new_html, 0, 1.0

    # Page similarity over word tokens of the page markup with script/style
    # blocks removed (tag names and attributes still count as tokens; only
    # the <script>/<style> payloads are dropped). A character-level
    # SequenceMatcher over the whole page is quadratic in its length, and a
    # page embedding htmlwidgets is megabytes of <script> JSON.
    similarity = difflib.SequenceMatcher(
        None,
        SCRIPT_STYLE_BLOCK_RE.sub(" ", norm_old).split(),
        SCRIPT_STYLE_BLOCK_RE.sub(" ", norm_new).split(),
    ).ratio()

    old_elements = ELEMENT_RE.findall(old_content)
    new_matches = list(ELEMENT_RE.finditer(new_content))

    old_elem_list = []
    skipped_elements = 0
    for elem in old_elements:
        text = extract_text_from_element(elem)
        if _comparable(elem, text):
            old_elem_list.append((text, normalize_text(text, patterns), elem))

    if len(old_elem_list) > MAX_ELEMENTS_FOR_PAIRWISE or len(new_matches) > MAX_ELEMENTS_FOR_PAIRWISE:
        print(
            annotate(
                "notice",
                f"Skipping element-level diff highlighting: "
                f"{len(old_elem_list)} old / {len(new_matches)} new candidate "
                f"elements exceed the {MAX_ELEMENTS_FOR_PAIRWISE}-element cap",
            ),
            file=sys.stderr,
        )
        return new_html, 0, similarity

    used_old_indices = set()
    replacements = []

    SIMILARITY_THRESHOLD_MIN = 0.5

    # Old element indices by normalized text, in document order. An unchanged
    # element (the common case) finds its first identical, still-unused twin
    # here in O(1) -- the same element the scan below reached, since a ratio
    # of 1.0 means identical sequences -- instead of via a ratio() against
    # every old element before it.
    old_indices_by_text = {}
    for idx, (_, norm_old_elem_text, _) in enumerate(old_elem_list):
        old_indices_by_text.setdefault(norm_old_elem_text, []).append(idx)

    for m in new_matches:
        new_elem = m.group(1)
        new_text = extract_text_from_element(new_elem)
        if not _comparable(new_elem, new_text):
            if new_text:
                skipped_elements += 1
            continue

        norm_new_elem_text = normalize_text(new_text, patterns)
        best_match_idx = None
        best_ratio = 0.0

        exact = next(
            (idx for idx in old_indices_by_text.get(norm_new_elem_text, ())
             if idx not in used_old_indices),
            None,
        )
        if exact is not None:
            best_match_idx = exact
            best_ratio = 1.0
        else:
            # The matcher keeps the new text as its second sequence, whose
            # index difflib builds once rather than once per candidate.
            # real_quick_ratio() and quick_ratio() are upper bounds on
            # ratio(), so a candidate whose bound cannot beat best_ratio is
            # skipped without changing which candidate wins (ties already
            # kept the first).
            matcher = difflib.SequenceMatcher(None)
            matcher.set_seq2(norm_new_elem_text)
            for idx, (old_text, norm_old_elem_text, old_elem) in enumerate(old_elem_list):
                if idx in used_old_indices:
                    continue
                if deadline is not None and time.monotonic() > deadline:
                    raise BudgetExceeded
                matcher.set_seq1(norm_old_elem_text)
                if matcher.real_quick_ratio() <= best_ratio:
                    continue
                if matcher.quick_ratio() <= best_ratio:
                    continue
                ratio = matcher.ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match_idx = idx

        if best_match_idx is not None and best_ratio >= 1.0:
            used_old_indices.add(best_match_idx)
            # Unchanged element
            continue

        if best_match_idx is not None and best_ratio >= SIMILARITY_THRESHOLD_MIN:
            used_old_indices.add(best_match_idx)
            old_text, _, old_elem = old_elem_list[best_match_idx]

            tag_match = re.match(r"(<[^>]+>)(.*)(</[^>]+>)", new_elem, re.DOTALL)
            old_tag_match = re.match(r"(<[^>]+>)(.*)(</[^>]+>)", old_elem, re.DOTALL)

            if tag_match and old_tag_match:
                open_tag, inner_content, close_tag = tag_match.groups()
                _, old_inner_content, _ = old_tag_match.groups()

                highlighted_inner = highlight_html_diff(old_inner_content, inner_content)
                if highlighted_inner != inner_content:
                    highlighted_elem = f"{open_tag}{highlighted_inner}{close_tag}"
                    replacements.append((m.start(), m.end(), highlighted_elem))

        elif (best_match_idx is None or best_ratio < SIMILARITY_THRESHOLD_MIN) and new_text:
            tag_match = re.match(r"(<[^>]+>)(.*)(</[^>]+>)", new_elem, re.DOTALL)
            if tag_match:
                open_tag, inner_content, close_tag = tag_match.groups()
                highlighted_elem = (
                    f'{open_tag}<mark class="preview-element-added" style="background-color: #cff4fc; color: inherit; padding: 1px 2px; border-radius: 2px;">{inner_content}</mark>{close_tag}'
                )
                replacements.append((m.start(), m.end(), highlighted_elem))

    if skipped_elements:
        print(
            f"  left {skipped_elements} element(s) unhighlighted: they embed "
            f"<script>/<style> content or exceed {MAX_ELEMENT_TEXT_CHARS} "
            f"characters of text (HIGHLIGHT_MAX_ELEMENT_CHARS)",
            file=sys.stderr,
        )

    if not replacements:
        return new_html, 0, similarity

    pieces = []
    cursor = 0
    for start, end, replacement in replacements:
        pieces.append(new_content[cursor:start])
        pieces.append(replacement)
        cursor = end
    pieces.append(new_content[cursor:])
    highlighted_main_content = "".join(pieces)

    highlighted_new_html = (
        new_html[:start_idx] + highlighted_main_content + new_html[end_idx:]
    )

    return highlighted_new_html, len(replacements), similarity


def render_modified_page_banner(similarity):
    """Render the banner for a modified page with highlighting legend."""
    change_pct = max(1, int(round((1.0 - similarity) * 100)))
    return (
        f"{PAGE_BANNER_START}\n"
        '<div class="preview-page-changes-banner" style="background: #f8f9fa; border-left: 4px solid #0d6efd; padding: 10px 15px; margin: 15px 0; border-radius: 4px;">\n'
        '    <p style="margin: 0;">\n'
        f"        <strong>📝 Preview Changes:</strong> This page has been modified in this pull request (~{change_pct}% of content changed).\n"
        "        <br>\n"
        "        <strong>🎨 Highlighting Legend:</strong> \n"
        '        <mark class="preview-text-changed" style="background-color: #fff3cd; color: inherit; padding: 1px 3px; border-radius: 2px;">Modified text (yellow)</mark> shows changed words/phrases, \n'
        '        <mark class="preview-text-added" style="background-color: #d1e7dd; color: inherit; padding: 1px 3px; border-radius: 2px;">added text (green)</mark> shows new content, and \n'
        '        <mark class="preview-element-added" style="background-color: #cff4fc; color: inherit; padding: 1px 3px; border-radius: 2px;">new sections (blue)</mark> highlight entirely new paragraphs.\n'
        "    </p>\n"
        "</div>\n"
        f"{PAGE_BANNER_END}\n"
    )


def render_new_page_banner():
    """Render the banner for a new page."""
    return (
        f"{PAGE_BANNER_START}\n"
        '<div class="preview-page-changes-banner" style="background: #f8f9fa; border-left: 4px solid #0d6efd; padding: 10px 15px; margin: 15px 0; border-radius: 4px;">\n'
        '    <p style="margin: 0;">\n'
        "        <strong>📝 Preview:</strong> This is a new page added in this pull request.\n"
        "    </p>\n"
        "</div>\n"
        f"{PAGE_BANNER_END}\n"
    )


def apply_page_banner(html_content, banner, target_path=None):
    """Insert or replace the page banner in HTML content."""
    if EXISTING_PAGE_BANNER_RE.search(html_content):
        return EXISTING_PAGE_BANNER_RE.sub(lambda _: banner.rstrip("\n"), html_content, count=1)

    for anchor in ANCHOR_RES:
        match = anchor.search(html_content)
        if match:
            return html_content[: match.end()] + "\n" + banner + html_content[match.end() :]

    path_label = target_path or "page"
    raise HighlightError(
        f"{path_label} has no <main> or <body> element to insert the banner after"
    )


def chapter_file(rendered_dir, chapter_id):
    """The local rendered HTML file corresponding to chapter_id."""
    direct = rendered_dir / f"{chapter_id}.html"
    if direct.is_file():
        return direct
    direct_html = rendered_dir / chapter_id
    if direct_html.is_file():
        return direct_html
    parent = (rendered_dir / chapter_id).parent
    stem = Path(chapter_id).name
    if parent.is_dir():
        matches = sorted(p for p in parent.iterdir() if p.is_file() and p.stem == stem)
        if matches:
            return matches[0]
    return None


def process_chapters(
    repo_dir,
    rendered_dir,
    changed_chapter_ids,
    remote,
    branch,
    subdir,
    patterns,
):
    """Process rendered HTML files and inject change highlighting."""
    ref = resolve_deployed_ref(repo_dir, remote, branch)
    if ref is None:
        reason = f"branch {branch!r} does not exist on remote {remote!r}"
        print(annotate("notice", f"Skipping HTML change highlighting: {reason}"))
        return 0

    available = published_paths(repo_dir, ref)
    prefix = subdir.strip("/")
    updated_count = 0
    total_deadline = time.monotonic() + TOTAL_TIME_BUDGET_SECONDS

    # Determine files to process
    if changed_chapter_ids:
        targets = []
        for cid in changed_chapter_ids:
            cf = chapter_file(rendered_dir, cid)
            if cf:
                targets.append(cf)
            else:
                print(annotate("warning", f"Chapter file not found for id {cid!r}"))
    else:
        targets = sorted(rendered_dir.glob("chapters/*.html"))

    for target_path in targets:
        relative = target_path.relative_to(rendered_dir)
        published_path = f"{prefix}/{relative.as_posix()}" if prefix else relative.as_posix()

        new_html = target_path.read_text(encoding="utf-8")

        if published_path not in available:
            # Page is new in PR
            print(f"  new page:  {relative.as_posix()}")
            banner = render_new_page_banner()
            updated_html = apply_page_banner(new_html, banner, target_path)
            target_path.write_text(updated_html, encoding="utf-8")
            updated_count += 1
            continue

        published_bytes = read_published(repo_dir, ref, published_path)
        try:
            old_html = published_bytes.decode("utf-8")
        except UnicodeDecodeError:
            print(annotate("warning", f"Could not decode published file {published_path!r} as UTF-8"))
            continue

        deadline = min(time.monotonic() + PAGE_TIME_BUDGET_SECONDS, total_deadline)
        try:
            highlighted_html, changes_made, similarity = highlight_changed_elements(
                old_html, new_html, patterns, deadline=deadline
            )
        except BudgetExceeded:
            print(annotate(
                "warning",
                f"Skipping HTML change highlighting for {relative.as_posix()}: "
                f"pairwise matching exceeded its time budget "
                f"(HIGHLIGHT_PAGE_BUDGET_SECONDS={PAGE_TIME_BUDGET_SECONDS:g}, "
                f"HIGHLIGHT_TOTAL_BUDGET_SECONDS={TOTAL_TIME_BUDGET_SECONDS:g})",
            ))
            continue

        if changes_made > 0:
            banner = render_modified_page_banner(similarity)
            final_html = apply_page_banner(highlighted_html, banner, target_path)
            target_path.write_text(final_html, encoding="utf-8")
            updated_count += 1
            print(
                f"  highlighted: {relative.as_posix()} ({changes_made} element(s) changed, ~{int(round((1-similarity)*100))}% diff)"
            )
        else:
            print(f"  unchanged (or metadata-only): {relative.as_posix()}")

    print(f"Processed {len(targets)} HTML file(s); updated {updated_count} page(s).")
    return updated_count


def main():
    # Line-buffer stdout: under CI it is a pipe, so a slow page would
    # otherwise print nothing until the step ends or is cancelled.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    rendered_dir_raw = os.getenv("RENDERED_DIR", "").strip()
    if not rendered_dir_raw:
        raise HighlightError("RENDERED_DIR is required")
    rendered_dir = Path(rendered_dir_raw)
    if not rendered_dir.is_dir():
        raise HighlightError(f"rendered directory {rendered_dir} does not exist")

    detection_status = os.getenv("DETECTION_STATUS", "").strip() or "compared"
    skip_reason = os.getenv("SKIP_REASON", "").strip()

    if detection_status == "skipped":
        print(annotate("notice", f"Skipping HTML change highlighting: {skip_reason}"))
        return 0

    raw_chapters = os.getenv("CHANGED_CHAPTERS", "").strip()
    changed_chapter_ids = []
    if raw_chapters:
        try:
            changed_chapter_ids = json.loads(raw_chapters)
        except json.JSONDecodeError as exc:
            raise HighlightError(f"CHANGED_CHAPTERS is not valid JSON: {exc}") from exc
        if not isinstance(changed_chapter_ids, list):
            raise HighlightError("CHANGED_CHAPTERS must be a JSON array")

        if detection_status == "compared" and len(changed_chapter_ids) == 0:
            print("No changed chapters reported; skipping HTML change highlighting.")
            return 0

    extra_patterns = [
        line.strip()
        for line in os.getenv("NORMALIZE_PATTERNS", "").splitlines()
        if line.strip()
    ]

    process_chapters(
        repo_dir=os.getenv("REPO_DIR", ".") or ".",
        rendered_dir=rendered_dir,
        changed_chapter_ids=changed_chapter_ids,
        remote=os.getenv("DEPLOYED_REMOTE", "").strip() or "origin",
        branch=os.getenv("DEPLOYED_BRANCH", "").strip() or "gh-pages",
        subdir=os.getenv("DEPLOYED_SUBDIR", ""),
        patterns=compile_patterns(extra_patterns),
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HighlightError as error:
        print(annotate("error", error), file=sys.stderr)
        sys.exit(1)
