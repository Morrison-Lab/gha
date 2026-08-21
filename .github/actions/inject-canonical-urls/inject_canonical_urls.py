#!/usr/bin/env python3
"""Inject `<link rel="canonical">` into a rendered altdoc/Quarto docs tree.

`altdoc-multiversion-docs.yml` deploys the same rendered site to several
paths -- `/dev/`, `/latest-tag/`, `/vX.Y.Z/`, `/pr-preview/pr-<N>/` -- so a
search engine sees N near-identical copies of every page with no signal about
which is authoritative (gha#332). The usual outcome is an archive or `/dev/`
outranking `/latest-tag/`, and a reader landing on docs for a version they are
not running.

Two behaviours, chosen by DEPLOY_KIND:

- ``preview``  -- PR previews get ``<meta name="robots" content="noindex">``
  rather than a canonical. A preview is ephemeral and its content is not the
  authoritative copy of anything, so the right request is "do not index this"
  rather than "index that other page instead".
- everything else -- each page gets a canonical pointing at its ``/latest-tag/``
  equivalent.

**A canonical is only emitted when the target actually exists.** The
``LATEST_TAG_MANIFEST`` file lists the pages currently deployed under
``/latest-tag/``; a page absent from it (a doc that exists only on the default
branch, say) gets a self-canonical instead. Pointing a canonical at a URL that
404s is worse than emitting none: it asks the indexer to credit a page that is
not there. When no manifest is supplied at all, every page self-canonicalizes,
which is the same conservative direction.

Failure is loud, per the reference implementation this borrows from
(`IndrajeetPatil/workflows`, MIT): a missing docs directory, a base URL that is
not `https://`, a tree containing zero HTML files, or a page with no insertion
point all abort rather than silently producing an untagged site. A check that
can pass by doing nothing is not a check.

Configuration (environment variables, set by action.yml):
  DOCS_DIR              Rendered site root to rewrite in place. Required.
  DOCS_BASE_URL         Site base URL, e.g. https://owner.github.io/repo/.
  DEPLOY_KIND           "preview" for PR previews; anything else canonicalizes.
  DEPLOY_SUBDIR         Path this build deploys to (e.g. "dev", "v1.2.0"),
                        used for the self-canonical fallback.
  LATEST_TAG_MANIFEST   Optional file listing /latest-tag/-relative HTML paths,
                        one per line. Absent/empty => self-canonical only.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Set

# `404.html` is excluded from the indexable set: it is served for URLs that do
# not exist, so canonicalizing it would point every miss at a real page.
NON_INDEXABLE = {"404.html"}

# Insert before `<title>` where there is one, falling back to `<head>`. Quarto
# emits both, but a hand-written or plugin-generated page may lack the title.
_TITLE_RE = re.compile(r"<title[\s>]", re.IGNORECASE)
_HEAD_RE = re.compile(r"<head[\s>]", re.IGNORECASE)
# A run already carrying a canonical is left alone rather than double-tagged --
# the verification pass below asserts exactly one per page, so a second tag
# would fail the build rather than being merely untidy.
_CANONICAL_RE = re.compile(r"<link[^>]+rel=[\"']?canonical", re.IGNORECASE)
_ROBOTS_NOINDEX_RE = re.compile(
    r"<meta[^>]+name=[\"']?robots[\"']?[^>]*content=[\"'][^\"']*noindex", re.IGNORECASE
)


def die(msg: str) -> "None":
    print(f"::error::{msg}", file=sys.stderr)
    raise SystemExit(1)


def normalize_base_url(raw: str) -> str:
    """Return the base URL with exactly one trailing slash, or abort."""
    base = (raw or "").strip()
    if not base:
        die("DOCS_BASE_URL is empty; cannot build canonical URLs.")
    if not base.startswith("https://"):
        die(f"DOCS_BASE_URL must start with https:// (got {base!r}).")
    return base.rstrip("/") + "/"


def html_files(docs_dir: Path) -> List[Path]:
    return sorted(p for p in docs_dir.rglob("*.html") if p.is_file())


def read_manifest(path: Optional[str]) -> Optional[Set[str]]:
    """Return the set of /latest-tag/-relative HTML paths, or None if unset.

    None and an empty set mean different things: None is "no manifest was
    supplied, self-canonicalize everything", while an empty set is "/latest-tag/
    exists and contains nothing", which reaches the same fallback by a
    different route. Both are safe; conflating them would only lose the
    ability to say which happened in the log.
    """
    if not path:
        return None
    manifest_path = Path(path)
    if not manifest_path.is_file():
        return None
    entries = {
        line.strip().lstrip("./")
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    return entries


def canonical_target(
    relpath: str, base_url: str, subdir: str, manifest: Optional[Set[str]]
) -> str:
    """URL this page should name as authoritative."""
    if manifest is not None and relpath in manifest:
        return f"{base_url}latest-tag/{relpath}"
    # Self-canonical: this build's own deployed URL. Still worth emitting --
    # it pins the page against query-string and index.html duplicates even
    # when there is no cross-version target to point at.
    prefix = f"{subdir.strip('/')}/" if subdir.strip("/") else ""
    return f"{base_url}{prefix}{relpath}"


def insertion_index(html: str, path: Path) -> int:
    """Byte offset to insert at: before `<title>`, else after `<head ...>`.

    `<title>` is preferred because inserting before it keeps the tag adjacent
    to the metadata block rather than wherever `<head>` happens to end, which
    on a Quarto page is several attributes later.
    """
    title = _TITLE_RE.search(html)
    if title:
        return title.start()
    head = _HEAD_RE.search(html)
    if not head:
        die(
            f"{path}: no <title> or <head> to insert into. Refusing to guess an "
            "insertion point -- a silently untagged page is the defect this "
            "action exists to prevent."
        )
    # `<head ...>` may carry attributes, so insert past the tag's own '>'.
    return html.index(">", head.start()) + 1


def process(
    docs_dir: Path,
    base_url: str,
    deploy_kind: str,
    subdir: str,
    manifest: Optional[Set[str]],
) -> int:
    pages = html_files(docs_dir)
    if not pages:
        die(f"No HTML files found under {docs_dir}; nothing was rendered?")
    changed = 0
    for page in pages:
        rel = page.relative_to(docs_dir).as_posix()
        html = page.read_text(encoding="utf-8", errors="surrogateescape")
        if rel in NON_INDEXABLE:
            continue
        if deploy_kind == "preview":
            if _ROBOTS_NOINDEX_RE.search(html):
                continue
            tag = '<meta name="robots" content="noindex">\n'
        else:
            if _CANONICAL_RE.search(html):
                continue
            href = canonical_target(rel, base_url, subdir, manifest)
            tag = f'<link rel="canonical" href="{href}">\n'
        idx = insertion_index(html, page)
        page.write_text(
            html[:idx] + tag + html[idx:], encoding="utf-8", errors="surrogateescape"
        )
        changed += 1
    return changed


def verify(docs_dir: Path, deploy_kind: str) -> None:
    """Re-scan and assert exactly one tag per indexable page.

    Separate from the insertion pass deliberately: the insertion pass can only
    report what it believed it did, while this reads the files back. An
    off-by-one in the insertion index produces a plausible-looking log and a
    broken page, and only a re-read catches it.
    """
    pattern = _ROBOTS_NOINDEX_RE if deploy_kind == "preview" else _CANONICAL_RE
    label = "robots=noindex" if deploy_kind == "preview" else "canonical"
    offenders = []
    for page in html_files(docs_dir):
        rel = page.relative_to(docs_dir).as_posix()
        if rel in NON_INDEXABLE:
            continue
        html = page.read_text(encoding="utf-8", errors="surrogateescape")
        n = len(pattern.findall(html))
        if n != 1:
            offenders.append(f"  {rel}: {n} {label} tags (want exactly 1)")
    if offenders:
        die(
            f"{len(offenders)} page(s) do not carry exactly one {label} tag:\n"
            + "\n".join(offenders)
        )


def main() -> int:
    docs_dir = Path(os.environ.get("DOCS_DIR", "").strip() or ".")
    if not docs_dir.is_dir():
        die(f"DOCS_DIR {docs_dir} is not a directory.")
    deploy_kind = os.environ.get("DEPLOY_KIND", "").strip().lower()
    subdir = os.environ.get("DEPLOY_SUBDIR", "").strip()
    base_url = normalize_base_url(os.environ.get("DOCS_BASE_URL", ""))
    manifest = read_manifest(os.environ.get("LATEST_TAG_MANIFEST", "").strip())

    if deploy_kind == "preview":
        print(f"PR preview build: marking pages under {docs_dir} noindex.")
    else:
        n = "no manifest" if manifest is None else f"{len(manifest)} page(s)"
        print(
            f"Canonicalizing {docs_dir} against /latest-tag/ ({n} listed); "
            f"pages absent there self-canonicalize under '{subdir or '/'}'."
        )
    changed = process(docs_dir, base_url, deploy_kind, subdir, manifest)
    verify(docs_dir, deploy_kind)
    print(f"Tagged {changed} page(s); verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
