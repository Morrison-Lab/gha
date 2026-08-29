#!/usr/bin/env bash
#
# Run this repo's diff-scoped checks over COMMITTED content, refusing rather
# than returning a clean verdict it did not earn.
#
# Three checks here read the commit graph, not the working tree:
# check-new-line-breaks, check-phi and check-typos. Each diffs against a base
# ref, so a staged or untracked file is invisible to every one of them -- and
# each then prints "no findings" over content it never examined, which is
# indistinguishable from a genuine pass. CLAUDE.md's Tests section records the
# measured case and the recurrence that motivated this wrapper (gha#740).
#
# Two guards, both refusing rather than degrading:
#
#   1. Uncommitted changes. Any modification, staged or not, and any untracked
#      non-ignored file, is content the checks cannot see. Commit first.
#      DIFF_SCOPED_ALLOW_DIRTY=1 proceeds anyway and still prints what is
#      unexamined, so the gap is stated rather than silent.
#
#   2. An unresolvable base ref. The three checks disagree about what an empty
#      base ref means -- new-line-breaks and typos skip entirely, phi scans the
#      whole tree -- so passing one through yields a different wrong answer per
#      check rather than an error. Refuse instead.
#
# Usage:  bash check-diff-scoped.sh [base-ref]
# Env:    DIFF_SCOPED_BASE_REF, DIFF_SCOPED_ALLOW_DIRTY
set -euo pipefail

die() { printf '%s\n' "$*" >&2; exit 2; }

git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || die "check-diff-scoped: not inside a git work tree."
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# Resolve the default branch from the repository rather than assuming 'main':
# a repo whose default is named otherwise would otherwise fail on a ref that
# does not exist, reported as if the base were wrong.
default_base=""
if head_ref="$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null)"; then
  default_base="${head_ref#refs/remotes/}"
fi
base_ref="${1:-${DIFF_SCOPED_BASE_REF:-$default_base}}"

[ -n "$base_ref" ] || die \
"check-diff-scoped: no base ref, and origin/HEAD is not set in this clone.
  Pass one explicitly:      bash check-diff-scoped.sh origin/<default-branch>
  Or teach the clone:       git remote set-head origin --auto
Refusing rather than passing an empty base ref through: the checks disagree
about what one means, so each would fail differently and none would say so."

git rev-parse --verify --quiet "${base_ref}^{commit}" >/dev/null \
  || die "check-diff-scoped: base ref '$base_ref' does not resolve to a commit."

# --porcelain covers staged and unstaged modifications plus untracked files,
# and honours .gitignore -- so ignored build output does not block a run.
dirty="$(git status --porcelain)"
if [ -n "$dirty" ]; then
  count="$(printf '%s\n' "$dirty" | wc -l | tr -d '[:space:]')"
  if [ "${DIFF_SCOPED_ALLOW_DIRTY:-}" = "1" ]; then
    printf 'check-diff-scoped: WARNING -- %s uncommitted path(s) are NOT examined by these checks:\n' "$count" >&2
    printf '%s\n' "$dirty" >&2
    printf 'Proceeding because DIFF_SCOPED_ALLOW_DIRTY=1. The verdict below covers committed content only.\n\n' >&2
  else
    printf 'check-diff-scoped: %s uncommitted path(s); these checks read the commit\n' "$count" >&2
    printf 'graph, so the lines below would be reported clean without being examined:\n' >&2
    printf '%s\n' "$dirty" >&2
    printf '\nCommit first, then re-run. To run anyway: DIFF_SCOPED_ALLOW_DIRTY=1\n' >&2
    exit 2
  fi
fi

status=0
unavailable=()

# A check that could not RUN is not a check that passed, and it is not a
# finding either. Conflating either way is the same silent-wrong-verdict this
# wrapper exists to prevent, so tool availability is probed up front and
# reported as its own outcome with its own exit status.
typos_available() {
  [ -n "${TYPOS_BIN_DIR:-}" ] && [ -x "${TYPOS_BIN_DIR}/typos" ] && return 0
  command -v typos >/dev/null 2>&1
}

run_check() {
  local label="$1" script="$2" probe="$3"
  shift 3
  if [ ! -f "$script" ]; then
    printf 'check-diff-scoped: %-18s SKIP (%s not present)\n' "$label" "$script"
    unavailable+=( "$label (script absent)" )
    return
  fi
  if [ -n "$probe" ] && ! "$probe"; then
    printf 'check-diff-scoped: %-18s UNAVAILABLE (required tool not installed)\n' "$label"
    unavailable+=( "$label (tool not installed)" )
    return
  fi
  printf 'check-diff-scoped: %-18s running against %s\n' "$label" "$base_ref"
  if env "$@" python3 "$script"; then
    printf 'check-diff-scoped: %-18s OK\n\n' "$label"
  else
    printf 'check-diff-scoped: %-18s FAILED\n\n' "$label" >&2
    status=1
  fi
}

run_check new-line-breaks check-new-line-breaks/check-new-line-breaks.py ""               "NLB_BASE_REF=$base_ref"
run_check phi             check-phi/check-phi.py                         ""               "PHI_BASE_REF=$base_ref"
run_check typos           check-typos/check-typos.py                     typos_available  "TYPOS_BASE_REF=$base_ref"

if [ ${#unavailable[@]} -gt 0 ]; then
  printf 'check-diff-scoped: %s check(s) did not run: %s\n' \
    "${#unavailable[@]}" "$(IFS='; '; printf '%s' "${unavailable[*]}")" >&2
  printf 'Install typos with check-typos/install-typos.sh, or run the missing check in CI.\n' >&2
  # Exit 3 only when nothing actually failed: a real finding outranks an
  # incomplete run, since the finding is actionable now.
  [ "$status" -eq 0 ] && exit 3
fi

exit "$status"
