#!/usr/bin/env bash
# Offline tests for scripts/sweep-runner-tmp.sh (gha#1495): it removes only
# stale, user-owned folders whose names match, and keeps recent or unrelated ones.
#
# Usage: bash .github/workflows/scripts/tests/run-sweep-runner-tmp-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
script="$repo_root/scripts/sweep-runner-tmp.sh"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
t="$work/tmp"
mkdir "$t"
failures=0

old() { touch -d '3 days ago' "$@"; }
mk() { # mk <name> <old|new>: a folder holding one file
  mkdir "$t/$1"
  echo x > "$t/$1/f"
  if [ "$2" = old ]; then old "$t/$1/f" "$t/$1"; fi
}
mk Rtmp_stale old
mk quarto-session_stale old
mk Rtmp_recent new
mk other_stale old
# Old folder holding a recently changed file: a running job still writes there.
mk Rtmp_active old
touch "$t/Rtmp_active/f"
old "$t/Rtmp_active"
# An old plain file matching a pattern is not a folder.
echo x > "$t/Rtmp_file"; old "$t/Rtmp_file"

out=$(SWEEP_TMP_DIRS="$t" "$script")
echo "$out"

expect() { # expect <name> <present|absent>
  local state=absent
  [ -e "$t/$1" ] && state=present
  if [ "$state" != "$2" ]; then
    echo "::error::$1: expected $2 but it is $state"
    failures=$((failures + 1))
  fi
}
expect Rtmp_stale absent
expect quarto-session_stale absent
expect Rtmp_recent present
expect other_stale present
expect Rtmp_active present
expect Rtmp_file present

# A bad age warns and removes nothing.
mk Rtmp_again old
SWEEP_TMP_DIRS="$t" SWEEP_TMP_MAX_AGE_HOURS=abc "$script" | grep -q '::warning::' || {
  echo "::error::bad age did not warn"; failures=$((failures + 1)); }
expect Rtmp_again present

# A missing directory is skipped without error.
SWEEP_TMP_DIRS="$work/none" "$script" > /dev/null || {
  echo "::error::missing dir failed"; failures=$((failures + 1)); }

if [ "$failures" -gt 0 ]; then echo "$failures failure(s)"; exit 1; fi
echo "all sweep-runner-tmp tests passed"
