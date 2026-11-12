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
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

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


def compile_all(patterns):
    return [diffscope.glob_to_regex(p) for p in patterns]


def matches(path, regexes):
    return any(r.match(path) for r in regexes)


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
    """The changed paths, a rename by its new name, or None without a base."""
    if diffscope.run_git(["rev-parse", "--verify", "-q", base + "^{commit}"]) is None:
        return None
    return diffscope.git_paths(["diff", "--name-only", "-M", base, "HEAD"])


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
    content = compile_all(diffscope.split_list(os.environ.get("PRC_CONTENT_PATHS", "")) or DEFAULT_CONTENT)
    infra = compile_all(diffscope.split_list(os.environ.get("PRC_INFRA_PATHS", "")) or DEFAULT_INFRA)
    ignore = diffscope.compile_ignores(
        BUILTIN_IGNORE + diffscope.split_list(os.environ.get("PRC_PATHS_IGNORE", "")))
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
