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

# Resolving is strictly weaker than sharing history, and the gap is the whole
# failure this script exists to prevent. Given a base ref with no merge base,
# check-new-line-breaks and check-typos return 0 without examining anything,
# and check-phi silently scans the whole tree -- so all three read as OK. A
# shallow clone is the ordinary way to reach that state, and this repo already
# treats one as a refusal elsewhere: check-secrets refuses rather than
# reporting a partial scan clean.
git merge-base "$base_ref" HEAD >/dev/null 2>&1 || die \
"check-diff-scoped: '$base_ref' shares no reachable history with HEAD.
A shallow clone is the usual cause: git fetch --unshallow (or --deepen=N).
Refusing rather than running: two of these checks return 0 when the diff
cannot be computed, and the third silently scans the whole tree instead."

# --porcelain covers staged and unstaged modifications plus untracked files,
# and honours .gitignore -- so ignored build output does not block a run.
#
# The flags are not redundant. A bare --porcelain obeys the caller's
# status.showUntrackedFiles, which contributors set to 'no' on noisy trees --
# and that setting alone makes an untracked file invisible here, defeating the
# exact case this guard exists for with nothing in the output saying so.
dirty="$(git status --porcelain --untracked-files=normal --ignore-submodules=none)"
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
# A plain counter and a string rather than an array: `${arr[@]}` on an empty
# array under `set -u` is the classic pre-4.4 hazard, and a stock macOS
# /bin/bash is 3.2 -- so the success path itself would abort there.
unavailable_count=0
unavailable_list=""

# A check that could not RUN is not a check that passed, and it is not a
# finding either. Conflating either way is the same silent-wrong-verdict this
# wrapper exists to prevent, so tool availability is probed up front.

# The two Python checks need an interpreter. Without this they report FAILED
# twice on a machine simply lacking python3 -- a toolchain block, which is
# what the hook's own header says gets a hook disabled.
python_available() { command -v python3 >/dev/null 2>&1; }

# check-typos resolves its binary ONLY from TYPOS_BIN_DIR, never from PATH, so
# a probe that accepted a PATH install would pass here and then fail inside the
# check -- reporting a finding where there is only a missing install, which
# under the hook blocks the push. Point TYPOS_BIN_DIR at the PATH copy instead,
# so an ordinary install works rather than being declared unavailable.
typos_available() {
  # check-typos.py is Python too, so the interpreter gates this check as much
  # as the binary does. Probing only for `typos` let a python3-less machine
  # report a FAILED check (exit 127 from env) instead of an unavailable one.
  python_available || return 1
  if [ -n "${TYPOS_BIN_DIR:-}" ] && [ -x "${TYPOS_BIN_DIR}/typos" ]; then
    return 0
  fi
  local found
  found="$(command -v typos 2>/dev/null)" || return 1
  [ -n "$found" ] || return 1
  TYPOS_BIN_DIR="$(cd "$(dirname "$found")" && pwd)"
  export TYPOS_BIN_DIR
}

note_unavailable() {
  unavailable_count=$(( unavailable_count + 1 ))
  if [ -z "$unavailable_list" ]; then
    unavailable_list="$1"
  else
    unavailable_list="$unavailable_list; $1"
  fi
}

run_check() {
  local label="$1" script="$2" probe="$3"
  shift 3
  if [ ! -f "$script" ]; then
    printf 'check-diff-scoped: %-18s SKIP (%s not present)\n' "$label" "$script"
    note_unavailable "$label (script absent)"
    return
  fi
  if [ -n "$probe" ] && ! "$probe"; then
    printf 'check-diff-scoped: %-18s UNAVAILABLE (required tool not installed)\n' "$label"
    note_unavailable "$label (tool not installed)"
    return
  fi
  printf 'check-diff-scoped: %-18s running against %s\n' "$label" "$base_ref"

  # Capture rather than stream, so the check's own admission that it examined
  # nothing can be read back. The merge-base gate above should make this
  # unreachable; it is kept because a check reporting 0 over an empty
  # examination is precisely the outcome this script must never pass on, and
  # one gate for it is one more than the wrapped checks have.
  # `out=$(cmd)` is a simple assignment, so under `set -e` a failing cmd
  # terminates the script THERE -- skipping the unavailable summary and the
  # exit logic entirely, and exiting with the check's own status by accident.
  # The `|| rc=$?` form makes it part of a list, which set -e does not act on.
  local out rc=0
  out="$(env "$@" python3 "$script" 2>&1)" || rc=$?
  printf '%s\n' "$out"
  # Two gates, and both are load-bearing.
  #
  # Only when rc is 0: a non-zero status is a FINDING, which outranks any
  # inference drawn from the text, and a finding is the thing that must never
  # be downgraded.
  #
  # And anchored to the emitting form, never a free-text search: these checks
  # print each violation with up to 77 characters of the offending line, so a
  # substring scan reclassifies a real finding whenever the flagged line
  # happens to quote the phrase -- which this repo's own prose does, in this
  # script's header and in CLAUDE.md. A guard against an unearned clean
  # verdict that produces one on the docs describing it is worse than none.
  if [ "$rc" -eq 0 ] \
    && printf '%s' "$out" | grep -qE '^::warning::(Skipping the |Could not diff against )'; then
    printf 'check-diff-scoped: %-18s EXAMINED NOTHING (see its own warning above)\n' "$label" >&2
    note_unavailable "$label (could not diff)"
    return
  fi
  if [ "$rc" -eq 0 ]; then
    printf 'check-diff-scoped: %-18s OK\n\n' "$label"
  else
    printf 'check-diff-scoped: %-18s FAILED\n\n' "$label" >&2
    status=1
  fi
}

run_check new-line-breaks check-new-line-breaks/check-new-line-breaks.py python_available "NLB_BASE_REF=$base_ref"
run_check phi             check-phi/check-phi.py                         python_available "PHI_BASE_REF=$base_ref"
run_check typos           check-typos/check-typos.py                     typos_available  "TYPOS_BASE_REF=$base_ref"

if [ "$unavailable_count" -gt 0 ]; then
  printf 'check-diff-scoped: %s check(s) did not run: %s\n' \
    "$unavailable_count" "$unavailable_list" >&2
  printf 'Install typos with check-typos/install-typos.sh, or run the missing check in CI.\n' >&2
  # Written as a full if rather than `[ ... ] && exit 3`: as the last command
  # of this block, a failing && list would terminate the script through set -e
  # instead of reaching the exit below. The value coincides today, which is
  # what makes the short form fragile rather than wrong.
  if [ "$status" -eq 0 ]; then
    exit 3
  fi
fi

exit "$status"
