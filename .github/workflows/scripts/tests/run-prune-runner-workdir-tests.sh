#!/usr/bin/env bash
# Offline tests for scripts/prune-runner-workdir.sh (gha#1352).
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
script="$root/scripts/prune-runner-workdir.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
fail=0

check() {
  if ! "$@"; then
    echo "::error::failed: $*" >&2
    fail=1
  fi
}

# A work folder with the current job's checkout, an old and a recent one, the
# runner's own _tool, and an R library (R_LIBS_USER) that is not a checkout.
make_work() {
  local w=$1
  mkdir -p "$w/current/current" "$w/old/old" "$w/recent/recent" \
    "$w/_tool/Python" "$w/R/library/pkg"
  touch -d '30 days ago' "$w/old" "$w/R" "$w/_tool"
}

# Pass 1 alone: plenty of free space, so only the stale checkout goes.
w="$tmp/age"
make_work "$w"
GITHUB_WORKSPACE="$w/current/current" PRUNE_MIN_FREE_GB=0 bash "$script" > "$tmp/out1"
check test ! -e "$w/old"
check test -d "$w/recent/recent"
check test -d "$w/current/current"
check test -d "$w/_tool/Python"
check test -d "$w/R/library/pkg"

# Pass 2: a free-space floor no disk meets, so every other checkout goes, but
# never the current one, _tool, or the R library.
w="$tmp/full"
make_work "$w"
GITHUB_WORKSPACE="$w/current/current" PRUNE_MIN_FREE_GB=999999999 bash "$script" > "$tmp/out2"
check test ! -e "$w/old"
check test ! -e "$w/recent"
check test -d "$w/current/current"
check test -d "$w/_tool/Python"
check test -d "$w/R/library/pkg"
check grep -q 'still has under' "$tmp/out2"

# A missing or malformed workspace prunes nothing and still exits 0.
w="$tmp/bad"
make_work "$w"
check env GITHUB_WORKSPACE='' bash "$script"
check env GITHUB_WORKSPACE="$w/current/current" PRUNE_MAX_AGE_DAYS=x bash "$script"
check test -d "$w/old/old"

exit "$fail"
