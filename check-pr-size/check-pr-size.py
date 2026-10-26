#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Fail a pull request that changes more files or lines than the cap allows.

Every PR should be as small and focused as it can be while completely solving
its stated task (Ezra, 2026-10-23, gha#1188). A sweep goes out as minimal
batches, one PR per batch. Diff-scoped: merge base against HEAD. With no
usable base the check skips with a warning, as its siblings do.

Env (all optional except where noted):
  PRS_BASE_REF      ref to diff against (HEAD^1 on a pull request)
  PRS_MAX_FILES     file cap (default 10)
  PRS_MAX_LINES     added plus deleted line cap (default 300)
  PRS_PATHS_IGNORE  comma/newline-separated globs not counted
  PRS_EXEMPT        'true' when the PR carries the exemption label
  PRS_FAIL          'false' to warn instead of block (default true)
"""
import fnmatch
import os
import re
import subprocess
import sys

DEFAULT_MAX_FILES = 10
DEFAULT_MAX_LINES = 300
# Generated, lock, data and image paths a human does not hand-write.
BUILTIN_IGNORE = [
    "**/*.lock", "*.lock", "renv.lock", "**/renv.lock", "package-lock.json",
    "**/package-lock.json", "_freeze/**", "**/_freeze/**", "**/*.png",
    "**/*.jpg", "**/*.jpeg", "**/*.gif", "**/*.svg", "**/*.pdf",
    "**/*.csv", "**/*.rds", "**/*.RData", "**/*.min.js", "docs/**",
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


def is_ignored(path, regexes):
    return any(r.match(path) for r in regexes)


def parse_numstat(text):
    """Return [(path, changed_lines)] from `git diff --numstat` output."""
    rows = []
    for line in text.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if " => " in path:
            path = re.sub(r"\{[^}]* => ([^}]*)\}", r"\1", path)
            path = path.split(" => ")[-1]
        lines = 0 if added == "-" else int(added) + int(deleted)
        rows.append((path.replace("//", "/"), lines))
    return rows


def measure(rows, regexes):
    kept = [(p, n) for p, n in rows if not is_ignored(p, regexes)]
    return len(kept), sum(n for _, n in kept), kept


def verdict(files, lines, max_files, max_lines):
    problems = []
    if files > max_files:
        problems.append(f"{files} files changed (cap {max_files})")
    if lines > max_lines:
        problems.append(f"{lines} lines changed (cap {max_lines})")
    return problems


def read_int(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    if not re.fullmatch(r"[0-9]+", raw) or int(raw) < 1:
        print(f"::error::{name} must be a positive integer, got {raw!r}")
        sys.exit(2)
    return int(raw)


def diff_rows(base):
    ok = subprocess.run(["git", "rev-parse", "--verify", "-q", base + "^{commit}"],
                        capture_output=True, text=True)
    if ok.returncode != 0:
        return None
    out = subprocess.run(["git", "diff", "--numstat", "-M", base, "HEAD"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return parse_numstat(out.stdout)


def main():
    base = os.environ.get("PRS_BASE_REF", "").strip()
    fail = os.environ.get("PRS_FAIL", "true").strip().lower() != "false"
    max_files = read_int("PRS_MAX_FILES", DEFAULT_MAX_FILES)
    max_lines = read_int("PRS_MAX_LINES", DEFAULT_MAX_LINES)
    if not base:
        print("::warning::check-pr-size: no base-ref, skipping rather than "
              "measuring the whole tree.")
        return 0
    rows = diff_rows(base)
    if rows is None:
        print(f"::warning::check-pr-size: cannot diff against {base!r} "
              "(shallow checkout?), skipping.")
        return 0
    patterns = BUILTIN_IGNORE + parse_patterns(os.environ.get("PRS_PATHS_IGNORE", ""))
    regexes = [glob_to_regex(p) for p in patterns]
    files, lines, _ = measure(rows, regexes)
    print(f"check-pr-size: {files} file(s), {lines} changed line(s) "
          f"(caps {max_files} files, {max_lines} lines).")
    problems = verdict(files, lines, max_files, max_lines)
    if not problems:
        return 0
    if os.environ.get("PRS_EXEMPT", "").strip().lower() == "true":
        print("check-pr-size: over the cap, but the PR carries the exemption label.")
        return 0
    level = "error" if fail else "warning"
    print(f"::{level}::This PR is too large: {'; '.join(problems)}. "
          "Split it into minimal batches, one PR per batch of one concern, "
          "each as small as it can be while completely solving its task.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
