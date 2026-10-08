#!/usr/bin/env python3
"""Drop the frozen results a restored `_freeze` cache holds for changed pages.

Why this exists
---------------
`freeze: auto` decides whether a page's frozen results are stale by hashing
the page's own source file only. A page that pulls in a subfile through
`{{< include >}}`, or reads a data file or sourced script, keeps serving its
old results when only that dependency changes. Repositories worked around it
with the `clear freezer` label, which throws away the whole cache and
re-executes every page, so a one-line edit to a subfile cost a full render.

This script makes the cache safe to keep. The restored cache's key names the
commit it was rendered from (`quarto-freezer-<os>-<lock>-<sha>-<attempt>`), so
the script diffs that commit's tree against `HEAD` and removes the frozen
results of each page that changed, along with every page that:

- includes a changed file, directly or through another include; or
- mentions the name of a changed file that is not itself a page, anywhere in
  its own source or its includes, which catches `read.csv("data/x.csv")`,
  `source("R/f.R")` and the like.

The second rule over-matches on purpose: an unneeded re-execution costs
seconds, and a missed one publishes stale output.

Every failure degrades toward re-executing more, never less. When the key
names no commit, or that commit cannot be fetched, the whole `_freeze`
directory is removed and the render starts clean, as it would with no cache.

Environment variables
---------------------
PROJECT_DIR : the Quarto project directory (default: `.`).
FREEZE_DIR  : the freezer to prune (default: `<PROJECT_DIR>/_freeze`).
MATCHED_KEY : the key `actions/cache/restore` actually restored
              (its `cache-matched-key` output). Empty means nothing was
              restored, and the script does nothing.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

KEY_SHA_RE = re.compile(r"-([0-9a-f]{40})-\d+$")

# {{< include path >}}, with the path bare or in either kind of quotes.
INCLUDE_RE = re.compile(
    r"""\{\{<\s*include\s+(?:"([^"]+)"|'([^']+)'|([^"'>\s]+))\s*>\}\}"""
)

PAGE_SUFFIXES = {".qmd", ".rmd", ".ipynb", ".md"}
SKIP_DIRS = {"renv", "node_modules"}


def git(*args, cwd):
    """Run git, returning stdout, or None when the command fails."""
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def changed_paths(source_sha, repo_root):
    """Repo-relative paths that differ between `source_sha` and `HEAD`.

    A plain two-tree diff: it needs both commits' trees and no history in
    between, so one shallow fetch of `source_sha` is enough. Returns None
    when the commit cannot be reached.
    """
    if git("cat-file", "-e", f"{source_sha}^{{commit}}", cwd=repo_root) is None:
        git("fetch", "--quiet", "--no-tags", "--depth=1", "origin", source_sha,
            cwd=repo_root)
    diff = git("diff", "--name-only", "--no-renames", source_sha, "HEAD",
               cwd=repo_root)
    if diff is None:
        return None
    return {line for line in diff.splitlines() if line}


def dependencies(page, project_dir, _seen=None):
    """The page plus every file it includes, recursively, as resolved paths.

    An include that resolves to nothing is still recorded, so deleting a
    subfile invalidates the page that included it.
    """
    seen = set() if _seen is None else _seen
    page = page.resolve()
    if page in seen:
        return seen
    seen.add(page)
    try:
        text = page.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return seen
    for match in INCLUDE_RE.finditer(text):
        target = next(group for group in match.groups() if group)
        # Quarto resolves a leading `/` against the project root.
        base = project_dir if target.startswith("/") else page.parent
        dependencies(base / target.lstrip("/"), project_dir, seen)
    return seen


def frozen_pages(freeze_dir, project_dir):
    """Map each frozen page's source file to its `_freeze` directory.

    Quarto mirrors the source path without its extension:
    `chapters/intro.qmd` freezes to `_freeze/chapters/intro/`.
    """
    pages = {}
    for root, dirs, files in os.walk(project_dir):
        # Quarto renders nothing under `_` or `.` directories, and a package
        # library (renv, node_modules) can hold many thousands of files.
        dirs[:] = [d for d in dirs
                   if not d.startswith(("_", ".")) and d not in SKIP_DIRS]
        for name in files:
            path = Path(root) / name
            if path.suffix.lower() not in PAGE_SUFFIXES:
                continue
            frozen = freeze_dir / path.relative_to(project_dir).with_suffix("")
            if frozen.is_dir():
                pages[path.resolve()] = frozen
    return pages


def is_stale(deps, changed, changed_names):
    """Whether any dependency changed, or names a changed file."""
    if deps & changed:
        return True
    for dep in deps:
        try:
            text = dep.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(name in text for name in changed_names):
            return True
    return False


def wipe(freeze_dir, reason):
    print(f"::notice::Discarding the restored Quarto freeze: {reason}")
    shutil.rmtree(freeze_dir)


def main():
    project_dir = Path(os.getenv("PROJECT_DIR") or ".").resolve()
    freeze_dir = Path(os.getenv("FREEZE_DIR") or project_dir / "_freeze").resolve()
    matched_key = os.getenv("MATCHED_KEY", "").strip()

    if not matched_key or not freeze_dir.is_dir():
        print("No Quarto freeze was restored; nothing to prune.")
        return 0

    repo_root = git("rev-parse", "--show-toplevel", cwd=project_dir)
    if repo_root is None:
        wipe(freeze_dir, f"{project_dir} is not in a git work tree.")
        return 0
    repo_root = Path(repo_root).resolve()

    match = KEY_SHA_RE.search(matched_key)
    if match is None:
        wipe(freeze_dir, f"its key '{matched_key}' names no commit.")
        return 0
    source_sha = match.group(1)

    changed = changed_paths(source_sha, repo_root)
    if changed is None:
        wipe(freeze_dir, f"commit {source_sha} could not be fetched to diff against.")
        return 0
    print(f"Restored freeze was rendered from {source_sha}; "
          f"{len(changed)} file(s) differ from it.")
    if not changed:
        return 0

    changed_abs = {(repo_root / path).resolve() for path in changed}
    # Pages link to each other by file name, so matching a changed page's
    # name would invalidate every page that links to it. Pages and subfiles
    # are caught through the include graph instead.
    changed_names = {Path(path).name for path in changed
                     if Path(path).suffix.lower() not in PAGE_SUFFIXES}

    stale = []
    for page, frozen in sorted(frozen_pages(freeze_dir, project_dir).items()):
        if is_stale(dependencies(page, project_dir), changed_abs, changed_names):
            shutil.rmtree(frozen)
            stale.append(page.relative_to(project_dir))

    if stale:
        print(f"Removed frozen results for {len(stale)} page(s), "
              "which will re-execute:")
        for page in stale:
            print(f"  {page}")
    else:
        print("No frozen page depends on a changed file; keeping the whole freeze.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
