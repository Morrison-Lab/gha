#!/usr/bin/env bash
# Offline tests for scripts/check-runner-disk.sh (gha#1495): passes with enough
# free space, fails with a message naming the folder when short, and sweeps
# stale temp folders before deciding.
#
# Usage: bash .github/workflows/scripts/tests/run-check-runner-disk-tests.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
script="$repo_root/scripts/check-runner-disk.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0
fail() { echo "::error::$1"; failures=$((failures + 1)); }

CHECK_DISK_DIRS="$work" CHECK_DISK_MIN_FREE_GB=0 bash "$script" > /dev/null || fail "enough space should pass"

out=$(CHECK_DISK_DIRS="$work" CHECK_DISK_MIN_FREE_GB=999999999 SWEEP_TMP_DIRS="$work" bash "$script")
status=$?
[ "$status" = 1 ] || fail "short disk should exit 1, got $status"
case "$out" in *"$work has"*"GB free"*) ;; *) fail "message should name the folder: $out" ;; esac

mkdir "$work/Rtmp_old"; echo x > "$work/Rtmp_old/f"; touch -d '3 hours ago' "$work/Rtmp_old/f" "$work/Rtmp_old"
CHECK_DISK_DIRS="$work" CHECK_DISK_MIN_FREE_GB=999999999 SWEEP_TMP_DIRS="$work" bash "$script" > /dev/null
[ -e "$work/Rtmp_old" ] && fail "a short disk should sweep stale temp folders first"

# The hook seeds the tool cache next to the checkout's work folder (gha#1205).
version=$(python3 -c 'import platform; print(platform.python_version())')
case "$(uname -m)" in aarch64 | arm64) arch=arm64 ;; *) arch=x64 ;; esac
mkdir -p "$work/w/repo/repo"
(unset RUNNER_TOOL_CACHE; GITHUB_WORKSPACE="$work/w/repo/repo" CHECK_DISK_DIRS="$work" CHECK_DISK_MIN_FREE_GB=0 bash "$script" > /dev/null)
[ -f "$work/w/_tool/Python/$version/$arch.complete" ] || fail "the hook should seed Python into the work folder's _tool"

CHECK_DISK_MIN_FREE_GB=abc bash "$script" | grep -q '::warning::' || fail "bad threshold should warn"

# The hook runs from a private copy, so deleting the checkout's file mid-run
# cannot reach it (gha#1589), and it removes its copy when done.
copy=$(mktemp -d)
cp "$repo_root"/scripts/*.sh "$copy"
printf '%s\n' '#!/usr/bin/env bash' 'sleep 2' > "$copy/wait-runner-capacity.sh"
tmp_before=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'tmp.*' | wc -l)
(CHECK_DISK_DIRS="$work" CHECK_DISK_MIN_FREE_GB=0 bash "$copy/check-runner-disk.sh" > /dev/null) &
hook_pid=$!
sleep 1
rm "$copy/check-runner-disk.sh" "$copy/wait-runner-capacity.sh"
wait "$hook_pid" || fail "deleting the hook's file mid-run should not fail it"
tmp_after=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'tmp.*' | wc -l)
[ "$tmp_after" -le "$tmp_before" ] || fail "the private copy should be removed when the hook ends"
rm -rf "$copy"

[ "$failures" = 0 ] && echo "all check-runner-disk tests passed"
exit "$failures"
