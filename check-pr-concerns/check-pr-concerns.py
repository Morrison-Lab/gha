#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Fail a pull request that mixes lecture content with infrastructure.

Content and infrastructure changes go in separate PRs (standing rule; Ezra,
2026-10-23, gha#1188: every PR is as small and focused as it can be). Whether a
PR has a single concern cannot be decided mechanically; this is the proxy that
can: a PR that changes at least one content path and at least one
infrastructure path has two concerns. A path matching both lists counts as
infrastructure. Diff-scoped: merge base against HEAD. With no usable base the
check skips with a warning, as its siblings do.

Env (all optional):
  PRC_BASE_REF       ref to diff against (HEAD^1 on a pull request)
  PRC_CONTENT_PATHS  comma/newline-separated globs for content
  PRC_INFRA_PATHS    comma/newline-separated globs for infrastructure
  PRC_PATHS_IGNORE   comma/newline-separated globs counted as neither
  PRC_EXEMPT         'true' when the PR carries the exemption label
  PRC_FAIL           'false' to warn instead of block (default true)
"""
import os
import re
import subprocess
import sys

DEFAULT_CONTENT = ["chapters/**", "**/_subfiles/**", "**/*.qmd", "**/*.Rmd"]
DEFAULT_INFRA = [
    ".github/**", "tools/**", "scripts/**", "hooks/**", "filters/**",
    ".claude/**", "_quarto*.yml", "**/_quarto*.yml",
]
# Generated, lock and data paths belong to no concern.
BUILTIN_IGNORE = [
    "**/*.lock", "package-lock.json", "**/package-lock.json", "_freeze/**",
    "**/_freeze/**", "docs/**", "changelog.d/**",
]


def glob_to_regex(pattern):
    """Translate a glob with `*`, `?` and recursive `**` into a regex."""
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def parse_patterns(raw):
    return [p.strip() for p in re.split(r"[,\n]", raw) if p.strip()]


def compile_all(patterns):
    return [glob_to_regex(p) for p in patterns]


def matches(path, regexes):
    return any(r.match(path) for r in regexes)


def parse_names(text):
    """Return the changed paths from `git diff --name-status -M` output."""
    paths = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            paths.append(parts[-1])
    return paths


def classify(paths, content, infra, ignore):
    """Return (content_paths, infra_paths); infrastructure wins an overlap."""
    content_hits, infra_hits = [], []
    for path in paths:
        if matches(path, ignore):
            continue
        if matches(path, infra):
            infra_hits.append(path)
        elif matches(path, content):
            content_hits.append(path)
    return content_hits, infra_hits


def changed_paths(base):
    ok = subprocess.run(["git", "rev-parse", "--verify", "-q", base + "^{commit}"],
                        capture_output=True, text=True)
    if ok.returncode != 0:
        return None
    out = subprocess.run(["git", "diff", "--name-status", "-M", base, "HEAD"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return parse_names(out.stdout)


def sample(paths, limit=3):
    shown = ", ".join(f"`{p}`" for p in paths[:limit])
    return shown + (f" and {len(paths) - limit} more" if len(paths) > limit else "")


def main():
    base = os.environ.get("PRC_BASE_REF", "").strip()
    fail = os.environ.get("PRC_FAIL", "true").strip().lower() != "false"
    if not base:
        print("::warning::check-pr-concerns: no base-ref, skipping rather than "
              "examining the whole tree.")
        return 0
    paths = changed_paths(base)
    if paths is None:
        print(f"::warning::check-pr-concerns: cannot diff against {base!r} "
              "(shallow checkout?), skipping.")
        return 0
    content = compile_all(parse_patterns(os.environ.get("PRC_CONTENT_PATHS", "")) or DEFAULT_CONTENT)
    infra = compile_all(parse_patterns(os.environ.get("PRC_INFRA_PATHS", "")) or DEFAULT_INFRA)
    ignore = compile_all(BUILTIN_IGNORE + parse_patterns(os.environ.get("PRC_PATHS_IGNORE", "")))
    content_hits, infra_hits = classify(paths, content, infra, ignore)
    print(f"check-pr-concerns: {len(content_hits)} content file(s), "
          f"{len(infra_hits)} infrastructure file(s).")
    if not (content_hits and infra_hits):
        return 0
    if os.environ.get("PRC_EXEMPT", "").strip().lower() == "true":
        print("check-pr-concerns: mixes content and infrastructure, "
              "but the PR carries the exemption label.")
        return 0
    level = "error" if fail else "warning"
    print(f"::{level}::This PR mixes content ({sample(content_hits)}) with "
          f"infrastructure ({sample(infra_hits)}). Content and infrastructure "
          "go in separate PRs; split it, and stack the content PR on the "
          "infrastructure PR if it needs it.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
