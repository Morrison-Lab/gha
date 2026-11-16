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
The lines (not the files) of a newly added `_fig-*` subfile are not counted
(ai-config#4928), and neither is a path `.gitattributes` marks
`linguist-generated` (gha#1959).
  PRS_EXEMPT        'true' when the PR carries the exemption label
  PRS_PR_BODY       the PR description; one saying "mechanical,
                    content-identical" exempts the PR (ai-config#5129)
A pure rename (no line changed) does not count toward the file cap.
A diff that is a pure token substitution is exempt (gha#2050): every hunk
adds as many lines as it removes, and each changed line pair differs only by
one consistent map of at most MAX_SUBSTITUTIONS replacements, such as a
macro renamed across many files. The check prints the map.
  PRS_FAIL          'false' to warn instead of block (default true)
"""
import difflib
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

DEFAULT_MAX_FILES = 10
DEFAULT_MAX_LINES = 300
# Generated, lock, data and image paths a human does not hand-write.
BUILTIN_IGNORE = [
    "**/*.lock", "*.lock", "renv.lock", "**/renv.lock", "package-lock.json",
    "**/package-lock.json", "_freeze/**", "**/_freeze/**", "**/*.png",
    "**/*.jpg", "**/*.jpeg", "**/*.gif", "**/*.svg", "**/*.pdf",
    "**/*.csv", "**/*.rds", "**/*.RData", "**/*.min.js", "docs/**",
]

# New figure subfiles are plotting code in several languages. Their lines do not
# count toward the line cap, but each still counts as a file (ai-config#4928).
NEW_FIGURE_LINES_FREE = "**/_fig-*"


# A pure substitution (gha#2050) has at most this many distinct replacements.
MAX_SUBSTITUTIONS = 10
# A token is a backslash macro name, a word, a run of whitespace, or one other
# character, so renaming the macro `beta` to `coef` is one replacement however
# it is subscripted.
TOKEN_RE = re.compile(r"\\[A-Za-z]+|\w+|\s+|.")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")


def _hunks(diff):
    """Yield (path, removed lines, added lines) for each hunk of a `-U0` diff.

    A binary file yields (path, None, None), so the caller can refuse it.
    """
    path, removed, added, in_hunk = None, [], [], False
    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            if in_hunk:
                yield path, removed, added
            path, in_hunk = None, False
        elif not in_hunk and line.startswith("+++ "):
            target = diffscope.unquote_git_path(line[4:])
            path = None if target == "/dev/null" else target[2:]
        elif not in_hunk and line.startswith("Binary files "):
            yield path or line, None, None
        elif HUNK_RE.match(line):
            if in_hunk:
                yield path, removed, added
            removed, added, in_hunk = [], [], True
        elif in_hunk and line.startswith("-"):
            removed.append(line[1:])
        elif in_hunk and line.startswith("+"):
            added.append(line[1:])
    if in_hunk:
        yield path, removed, added


def _line_replacements(old, new):
    """The (old run, new run) pairs that turn `old` into `new`.

    None when a token is only inserted or only deleted, since that is an edit
    rather than a substitution.
    """
    a, b = TOKEN_RE.findall(old), TOKEN_RE.findall(new)
    found = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        old_run, new_run = "".join(a[i1:i2]), "".join(b[j1:j2])
        # A run holding whitespace spans words, so it can rewrite a whole
        # sentence as one entry; refusing it keeps each entry to one word.
        if op != "replace" or re.search(r"\s", old_run + new_run):
            return None
        found.append((old_run, new_run))
    return found


def substitution_map(diff, skip=lambda path: False):
    """The replacement map when `diff` is a pure substitution, else None.

    `diff` is `git diff -U0` output. A hunk in a path `skip` accepts is not
    examined. A diff with no examined hunk is not a substitution.
    """
    mapping = {}
    for path, removed, added in _hunks(diff):
        if path is not None and skip(path):
            continue
        if not removed or len(removed) != len(added):
            return None
        for old, new in zip(removed, added):
            found = _line_replacements(old, new)
            if not found:
                return None
            for key, value in found:
                if mapping.setdefault(key, value) != value:
                    return None
            if len(mapping) > MAX_SUBSTITUTIONS:
                return None
    return mapping or None


def substitution_diff(base):
    return diffscope.run_git(["-c", "core.quotepath=false", "diff", "-U0", "--no-color",
                              "--no-ext-diff", "-M", base, "HEAD"])


MECHANICAL_RE = re.compile(r"mechanical,\s*content-identical", re.IGNORECASE)


def states_mechanical(body):
    """True when the PR description says the change is mechanical and content-identical."""
    return bool(MECHANICAL_RE.search(body or ""))


def parse_numstat(text):
    """Return [(path, changed_lines)] from `git diff --numstat -z` output.

    `-z` leaves a name holding `"`, a backslash or a tab unquoted (gha#1923),
    and gives a rename's new name as its own field instead of `{a => b}`.
    """
    fields = text.split("\0")
    rows = []
    i = 0
    while i < len(fields):
        parts = fields[i].split("\t", 2)
        i += 1
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if not path:  # a rename: the old and new names follow
            path = fields[i + 1] if i + 1 < len(fields) else ""
            i += 2
        lines = 0 if added == "-" else int(added) + int(deleted)
        rows.append((path, lines))
    return rows


def measure(rows, regexes, added=frozenset(), renames=frozenset()):
    """File and line counts.

    The lines of a newly added figure subfile are free, and a pure rename
    (no line changed) does not count as a file (ai-config#5129).
    """
    free = diffscope.glob_to_regex(NEW_FIGURE_LINES_FREE)
    kept = [(p, n) for p, n in rows if not diffscope.ignored(p, regexes) and p not in renames]
    lines = sum(0 if p in added and free.match(p) else n for p, n in kept)
    return len(kept), lines, kept


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


def added_paths(base):
    """Paths the diff adds as new files (a rename is not an addition)."""
    paths = diffscope.git_paths(["diff", "--name-only", "--diff-filter=A", "-M", base, "HEAD"])
    return frozenset(paths or ())


def pure_renames(base):
    """New paths of renames with 100% similarity, so no line changed."""
    fields = diffscope.git_paths(["diff", "--name-status", "-M100%", base, "HEAD"]) or []
    renames = set()
    i = 0
    while i < len(fields):
        status = fields[i]
        if status[:1] in ("R", "C"):
            if status == "R100" and i + 2 < len(fields):
                renames.add(fields[i + 2])
            i += 3
        else:
            i += 2
    return frozenset(renames)


def generated_paths(paths):
    """The paths among `paths` that `.gitattributes` marks `linguist-generated`.

    A repo marks its committed generator outputs once, and GitHub folds them
    in review as well (gha#1959, ai-config#5288).
    """
    if not paths:
        return frozenset()
    out = subprocess.run(["git", "check-attr", "-z", "--stdin", "linguist-generated"],
                         input="\0".join(paths) + "\0", capture_output=True, text=True)
    if out.returncode != 0:
        print("::warning::check-pr-size: git check-attr failed, counting "
              "linguist-generated paths.")
        return frozenset()
    f = out.stdout.split("\0")
    return frozenset(f[i] for i in range(0, len(f) - 2, 3) if f[i + 2] in ("set", "true"))


def diff_rows(base):
    if diffscope.run_git(["rev-parse", "--verify", "-q", base + "^{commit}"]) is None:
        return None
    out = diffscope.run_git(["diff", "--numstat", "-z", "-M", base, "HEAD"])
    return None if out is None else parse_numstat(out)


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
    patterns = BUILTIN_IGNORE + diffscope.split_list(os.environ.get("PRS_PATHS_IGNORE", ""))
    regexes = diffscope.compile_ignores(patterns)
    generated = generated_paths([p for p, _ in rows])
    rows = [(p, n) for p, n in rows if p not in generated]
    files, lines, _ = measure(rows, regexes, added_paths(base), pure_renames(base))
    print(f"check-pr-size: {files} file(s), {lines} changed line(s) "
          f"(caps {max_files} files, {max_lines} lines).")
    problems = verdict(files, lines, max_files, max_lines)
    if not problems:
        return 0
    if os.environ.get("PRS_EXEMPT", "").strip().lower() == "true":
        print("check-pr-size: over the cap, but the PR carries the exemption label.")
        return 0
    diff = substitution_diff(base)
    mapping = None if diff is None else substitution_map(
        diff, lambda p: p in generated or diffscope.ignored(p, regexes))
    if mapping:
        print("check-pr-size: over the cap, but the diff is a pure substitution:")
        for old, new in mapping.items():
            print(f"  {old!r} -> {new!r}")
        return 0
    if states_mechanical(os.environ.get("PRS_PR_BODY", "")):
        print("check-pr-size: over the cap, but the PR says it is mechanical, "
              "content-identical.")
        return 0
    level = "error" if fail else "warning"
    print(f"::{level}::This PR is too large: {'; '.join(problems)}. "
          "Split it into minimal batches, one PR per batch of one concern, "
          "each as small as it can be while completely solving its task.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
