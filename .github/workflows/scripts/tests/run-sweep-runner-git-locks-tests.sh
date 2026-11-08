#!/usr/bin/env bash
# Offline tests for scripts/sweep-runner-git-locks.sh (gha#1661): it removes
# only stale *.lock files under a checkout's .git, .git/modules and .git/refs
# (gha#1716), and keeps
# recent locks, other files, and everything while a git process runs there.
#
# Usage: bash .github/workflows/scripts/tests/run-sweep-runner-git-locks-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
script="$repo_root/scripts/sweep-runner-git-locks.sh"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

mkdir -p "$work/epi204/epi204/.git/modules/rme" "$work/epi204/epi204/.git/refs/remotes/origin/claude" "$work/_tool/x/.git"
refs="$work/epi204/epi204/.git/refs/remotes/origin/claude"
old() { touch -d '3 hours ago' "$@"; }
echo x > "$work/epi204/epi204/.git/modules/rme/index.lock"; old "$work/epi204/epi204/.git/modules/rme/index.lock"
echo x > "$work/epi204/epi204/.git/index.lock"; old "$work/epi204/epi204/.git/index.lock"
echo x > "$work/epi204/epi204/.git/modules/rme/recent.lock"
echo x > "$work/epi204/epi204/.git/modules/rme/HEAD"; old "$work/epi204/epi204/.git/modules/rme/HEAD"
echo x > "$refs/branch.lock"; old "$refs/branch.lock"
echo x > "$refs/recent.lock"
echo x > "$work/epi204/epi204/not-in-git.lock"; old "$work/epi204/epi204/not-in-git.lock"
echo x > "$work/_tool/x/.git/stale.lock"; old "$work/_tool/x/.git/stale.lock"

expect() { # expect <path> <present|absent>
  local state=absent
  [ -e "$1" ] && state=present
  if [ "$state" != "$2" ]; then
    echo "::error::$1: expected $2 but it is $state"
    failures=$((failures + 1))
  fi
}

"$script" "$work"
expect "$work/epi204/epi204/.git/modules/rme/index.lock" absent
expect "$work/epi204/epi204/.git/index.lock" absent
expect "$refs/branch.lock" absent
expect "$refs/recent.lock" present
expect "$work/epi204/epi204/.git/modules/rme/recent.lock" present
expect "$work/epi204/epi204/.git/modules/rme/HEAD" present
expect "$work/epi204/epi204/not-in-git.lock" present
expect "$work/_tool/x/.git/stale.lock" present

# A git process working inside the work folder stops the sweep.
echo x > "$work/epi204/epi204/.git/index.lock"; old "$work/epi204/epi204/.git/index.lock"
# pgrep matches the process name, so the holder must really be named git.
fakebin=$(mktemp -d)
cp "$(command -v sleep)" "$fakebin/git"
(cd "$work/epi204/epi204" && exec "$fakebin/git" 30) &
holder=$!
sleep 1
"$script" "$work" | grep -q 'a git process is running' || {
  echo "::error::did not notice the running git process"; failures=$((failures + 1)); }
expect "$work/epi204/epi204/.git/index.lock" present
kill "$holder" 2> /dev/null || true
wait "$holder" 2> /dev/null || true

# A bad age warns and removes nothing.
SWEEP_LOCK_MIN_AGE_MINUTES=abc "$script" "$work" | grep -q '::warning::' || {
  echo "::error::bad age did not warn"; failures=$((failures + 1)); }
expect "$work/epi204/epi204/.git/index.lock" present

# A missing work folder warns without error.
"$script" "$work/none" | grep -q '::warning::' || {
  echo "::error::missing folder did not warn"; failures=$((failures + 1)); }

if [ "$failures" -gt 0 ]; then echo "$failures failure(s)"; exit 1; fi
echo "all sweep-runner-git-locks tests passed"
