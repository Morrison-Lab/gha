#!/usr/bin/env python3
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

Configuration (all via environment, set by `preview/action.yml`):

  RENDERED_DIR         Directory holding this run's rendered site. Required.
  CHANGED_CHAPTERS     JSON array of changed chapter ids. Default `[]`.
  DETECTION_STATUS     `compared` or `skipped`. Default `compared`.
  SKIP_REASON          Why comparison was skipped; empty when compared.
  CHAPTER_GLOB         Glob selecting rendered files when CHANGED_CHAPTERS is unset.
                       Default `chapters/*.html`.
  DEPLOYED_REMOTE      Git remote holding published site. Default `origin`.
  DEPLOYED_BRANCH      Branch on that remote. Default `gh-pages`.
  DEPLOYED_SUBDIR      Path prefix, within deployed branch, at which site root lives.
                       Default '' (the branch root).
  NORMALIZE_PATTERNS   Newline-separated regexes whose matches are blanked before
                       comparison, in addition to built-in defaults.
  REPO_DIR             Git repository to run in. Default `.`.
"""

import difflib
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from _workflow_annotations import annotate

DEFAULT_NORMALIZE_PATTERNS = (
    # htmlwidgets/plotly mint a fresh random element id on every render.
    r"htmlwidget[-_][0-9a-f]{6,}",
    # Machine-written ISO-8601 datetimes (build stamps), which always carry a time component.
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?",
)

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
PLACEHOLDER = "GHA-VOLATILE"


class HighlightError(RuntimeError):
    """A condition that must stop the run."""


def run_git(args, repo_dir):
    """Run a git command, raising on any non-zero exit."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")
        raise HighlightError(
            f"`git {' '.join(args)}` failed with exit {result.returncode}: {stderr.strip()}"
        )
    return result.stdout


def resolve_deployed_ref(repo_dir, remote, branch):
    """Fetch deployed branch and return local ref for it, or None if absent."""
    listing = run_git(
        ["ls-remote", "--heads", remote, f"refs/heads/{branch}"], repo_dir
    ).decode("utf-8", "replace")
    if not listing.strip():
        return None

    local_ref = f"refs/gha-preview-base/{branch}"
    run_git(
        [
            "fetch",
            "--no-tags",
            "--depth=1",
            remote,
            f"+refs/heads/{branch}:{local_ref}",
        ],
        repo_dir,
    )
    return local_ref


def published_paths(repo_dir, ref):
    """Every blob path in the deployed tree."""
    listing = run_git(["ls-tree", "-r", "--name-only", "-z", ref], repo_dir)
    return {p for p in listing.decode("utf-8", "replace").split("\0") if p}


def read_published(repo_dir, ref, path):
    """Read published blob bytes from git."""
    return run_git(["cat-file", "blob", f"{ref}:{path}"], repo_dir)


def compile_patterns(extra_patterns):
    """Compile normalization patterns, rejecting empty matches."""
    compiled = []
    for raw in [*DEFAULT_NORMALIZE_PATTERNS, *extra_patterns]:
        try:
            pattern = re.compile(raw)
        except re.error as exc:
            raise HighlightError(f"invalid normalize pattern {raw!r}: {exc}") from exc
        if pattern.search(""):
            raise HighlightError(
                f"normalize pattern {raw!r} matches empty string, which would "
                "blank every document"
            )
        compiled.append(pattern)
    return compiled


def normalize_text(text, patterns):
    """Normalize text/HTML for comparison."""
    for pattern in patterns:
        text = pattern.sub(PLACEHOLDER, text)
    # Remove HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_main_content(html_str):
    """Extract main content section from HTML, ignoring navigation and metadata."""
    main_match = re.search(r"<main[^>]*>(.*?)</main>", html_str, re.DOTALL | re.IGNORECASE)
    if main_match:
        return main_match.group(1)

    content_div = re.search(
        r'<div[^>]*id=["\']quarto-document-content["\'][^>]*>(.*?)</div>',
        html_str,
        re.DOTALL | re.IGNORECASE,
    )
    if content_div:
        return content_div.group(1)

    fallback_div = re.search(
        r'<div[^>]*class=["\'][^"\']*content[^"\']*["\'][^>]*>(.*?)</div>',
        html_str,
        re.DOTALL | re.IGNORECASE,
    )
    if fallback_div:
        return fallback_div.group(1)

    body_match = re.search(r"<body[^>]*>(.*?)</body>", html_str, re.DOTALL | re.IGNORECASE)
    if body_match:
        return body_match.group(1)

    return html_str


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


def highlight_changed_elements(old_html, new_html, patterns):
    """Find and highlight changed paragraphs and sections in the HTML.

    Returns (highlighted_html, changes_count, similarity_ratio).
    """
    old_content = extract_main_content(old_html)
    new_content = extract_main_content(new_html)

    norm_old = normalize_text(old_content, patterns)
    norm_new = normalize_text(new_content, patterns)

    if norm_old == norm_new:
        return new_html, 0, 1.0

    similarity = difflib.SequenceMatcher(None, norm_old, norm_new).ratio()

    old_elements = ELEMENT_RE.findall(old_content)
    new_elements = ELEMENT_RE.findall(new_content)

    old_elem_list = []
    for elem in old_elements:
        text = extract_text_from_element(elem)
        if text:
            old_elem_list.append((text, normalize_text(text, patterns), elem))

    used_old_indices = set()
    highlighted_new_html = new_html
    changes_made = 0

    SIMILARITY_THRESHOLD_MIN = 0.5
    SIMILARITY_THRESHOLD_MAX = 0.999

    for new_elem in new_elements:
        new_text = extract_text_from_element(new_elem)
        if not new_text:
            continue

        norm_new_elem_text = normalize_text(new_text, patterns)
        best_match_idx = None
        best_ratio = 0.0

        for idx, (old_text, norm_old_elem_text, old_elem) in enumerate(old_elem_list):
            if idx in used_old_indices:
                continue

            if norm_old_elem_text == norm_new_elem_text:
                best_match_idx = idx
                best_ratio = 1.0
                break

            ratio = difflib.SequenceMatcher(None, norm_old_elem_text, norm_new_elem_text).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match_idx = idx

        if best_match_idx is not None and best_ratio >= 1.0:
            used_old_indices.add(best_match_idx)
            # Unchanged element
            continue

        if (
            best_match_idx is not None
            and SIMILARITY_THRESHOLD_MIN <= best_ratio < SIMILARITY_THRESHOLD_MAX
        ):
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
                    highlighted_new_html = highlighted_new_html.replace(
                        new_elem, highlighted_elem, 1
                    )
                    changes_made += 1

        elif (best_match_idx is None or best_ratio < SIMILARITY_THRESHOLD_MIN) and new_text:
            tag_match = re.match(r"(<[^>]+>)(.*)(</[^>]+>)", new_elem, re.DOTALL)
            if tag_match:
                open_tag, inner_content, close_tag = tag_match.groups()
                highlighted_elem = (
                    f'{open_tag}<mark class="preview-element-added" style="background-color: #cff4fc; color: inherit; padding: 1px 2px; border-radius: 2px;">{inner_content}</mark>{close_tag}'
                )
                highlighted_new_html = highlighted_new_html.replace(
                    new_elem, highlighted_elem, 1
                )
                changes_made += 1

    return highlighted_new_html, changes_made, similarity


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


def apply_page_banner(html_content, banner):
    """Insert or replace the page banner in HTML content."""
    if EXISTING_PAGE_BANNER_RE.search(html_content):
        return EXISTING_PAGE_BANNER_RE.sub(lambda _: banner.rstrip("\n"), html_content, count=1)

    for anchor in ANCHOR_RES:
        match = anchor.search(html_content)
        if match:
            return html_content[: match.end()] + "\n" + banner + html_content[match.end() :]

    return banner + html_content


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
            updated_html = apply_page_banner(new_html, banner)
            target_path.write_text(updated_html, encoding="utf-8")
            updated_count += 1
            continue

        published_bytes = read_published(repo_dir, ref, published_path)
        try:
            old_html = published_bytes.decode("utf-8")
        except UnicodeDecodeError:
            print(annotate("warning", f"Could not decode published file {published_path!r} as UTF-8"))
            continue

        highlighted_html, changes_made, similarity = highlight_changed_elements(
            old_html, new_html, patterns
        )

        if changes_made > 0:
            banner = render_modified_page_banner(similarity)
            final_html = apply_page_banner(highlighted_html, banner)
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
