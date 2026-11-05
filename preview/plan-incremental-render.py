#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Decide whether a preview can render only the pages a PR changed.

Why this exists
---------------
A preview normally runs one full `quarto render`, which costs 10-60 s for
every page even when the page is frozen. With a cached `_site` and `.quarto`
restored from an earlier build, only the pages the PR can affect need to run
again. The restored cache's key names the commit it was rendered from, so this
script diffs that commit against `HEAD` (as `prune-stale-freeze.py` does) and
lists the pages to re-render: each page that changed, plus each page that
includes a changed file or names a changed non-page file.

Every doubt degrades toward the full render. The script chooses `full` when:

- the key names no commit, that commit cannot be fetched, or the cached
  `_site` or `.quarto` is missing;
- a changed path matches `FULL_PATTERNS` (configuration, extensions, filters,
  themes, the bibliography, shared macros, tooling);
- a changed path is neither ignored nor reachable from any rendered page, so
  the script cannot say what it affects;
- a rendered page was deleted, since its output would stay in `_site`;
- more than `MAX_PAGES` pages are stale.

Tradeoff: a page that is not re-rendered keeps its old navigation, search
entry and cross-reference numbers, so those can be stale in the preview.

Environment variables
---------------------
PROJECT_DIR   : the Quarto project directory (default: `.`).
MATCHED_KEY   : the key `actions/cache/restore` restored; empty means none.
INSPECT_JSON  : path to the output of `quarto inspect`, whose
                `files.input` lists the project's rendered pages.
FULL_PATTERNS : newline-separated globs (fnmatch, against the repo-relative
                path) that force a full render.
IGNORE_PATTERNS : newline-separated globs for paths that affect no page.
MAX_PAGES     : stale-page count above which the full render is cheaper.
PAGES_FILE    : where to write the page list, one project-relative path per
                line (default: `<PROJECT_DIR>/_incremental_pages.txt`).
GITHUB_OUTPUT : receives `mode` (`full` or `incremental`) and `reason`.
"""

import fnmatch
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_pruner():
    """Import the freeze pruner, whose hyphenated file name is not importable."""
    spec = importlib.util.spec_from_file_location(
        "prune_stale_freeze", HERE / "prune-stale-freeze.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def patterns(value):
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def matches(path, globs):
    """Whether `path` matches a glob; a trailing `/` matches a directory prefix."""
    for glob in globs:
        if glob.endswith("/"):
            if path.startswith(glob) or f"/{glob}" in f"/{path}":
                return True
        elif fnmatch.fnmatch(path, glob) or fnmatch.fnmatch(Path(path).name, glob):
            return True
    return False


def decide(project_dir, matched_key, inspect_json, full_globs, ignore_globs,
           max_pages, pruner):
    """Return (mode, reason, pages), pages being project-relative paths."""
    if not matched_key:
        return "full", "no incremental cache was restored", []
    for cached in ("_site", ".quarto"):
        if not (project_dir / cached).is_dir():
            return "full", f"the restored cache has no {cached}", []
    match = pruner.KEY_SHA_RE.search(matched_key)
    if match is None:
        return "full", f"cache key '{matched_key}' names no commit", []
    repo_root = pruner.git("rev-parse", "--show-toplevel", cwd=project_dir)
    if repo_root is None:
        return "full", f"{project_dir} is not in a git work tree", []
    repo_root = Path(repo_root).resolve()
    changed = pruner.changed_paths(match.group(1), repo_root)
    if changed is None:
        return "full", f"commit {match.group(1)} could not be fetched", []

    try:
        inspected = json.loads(Path(inspect_json).read_text(encoding="utf-8"))
        inputs = [Path(p).resolve() for p in inspected["files"]["input"]]
    except (OSError, ValueError, KeyError, TypeError):
        return "full", "`quarto inspect` did not list the project's pages", []

    deps = {page: pruner.dependencies(page, project_dir) for page in inputs}
    reachable = set().union(*deps.values()) if deps else set()
    texts = []
    for dep in reachable:
        try:
            texts.append(dep.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue

    changed_abs = {(repo_root / path).resolve() for path in changed}
    changed_names = {Path(path).name for path in changed
                     if Path(path).suffix.lower() not in pruner.PAGE_SUFFIXES}

    for path in sorted(changed):
        absolute = (repo_root / path).resolve()
        if matches(path, full_globs):
            return "full", f"{path} can affect every page", []
        if matches(path, ignore_globs):
            continue
        if absolute in reachable:
            continue
        if Path(path).suffix.lower() in pruner.PAGE_SUFFIXES:
            # A page-type file no rendered page reaches affects nothing,
            # unless it was a page: `inputs` comes from HEAD, where a deleted
            # page is already gone, so its output would stay in `_site`.
            if not absolute.exists() and not path.startswith("_") and "/_" not in path:
                return "full", f"page {path} was deleted", []
            continue
        if any(Path(path).name in text for text in texts):
            continue
        return "full", f"{path} is not reachable from any rendered page", []

    stale = [page for page in inputs
             if pruner.is_stale(deps[page], changed_abs, changed_names)]
    if len(stale) > max_pages:
        return "full", f"{len(stale)} pages are stale (more than {max_pages})", []
    pages = sorted(str(page.relative_to(project_dir)) for page in stale)
    return "incremental", f"{len(pages)} stale page(s) of {len(inputs)}", pages


def main():
    project_dir = Path(os.getenv("PROJECT_DIR") or ".").resolve()
    pruner = _load_pruner()
    mode, reason, pages = decide(
        project_dir,
        os.getenv("MATCHED_KEY", "").strip(),
        os.getenv("INSPECT_JSON", ""),
        patterns(os.getenv("FULL_PATTERNS")),
        patterns(os.getenv("IGNORE_PATTERNS")),
        int(os.getenv("MAX_PAGES") or 15),
        pruner,
    )
    pages_file = Path(os.getenv("PAGES_FILE") or project_dir / "_incremental_pages.txt")
    pages_file.write_text("".join(f"{page}\n" for page in pages), encoding="utf-8")
    print(f"Incremental render plan: {mode} ({reason}).")
    for page in pages:
        print(f"  {page}")
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"mode={mode}\nreason={reason}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
