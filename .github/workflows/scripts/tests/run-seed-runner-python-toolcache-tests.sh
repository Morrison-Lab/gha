#!/usr/bin/env bash
# Offline tests for scripts/seed-runner-python-toolcache.sh (gha#1205).
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
script="$root/scripts/seed-runner-python-toolcache.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
fail=0

check() {
  if ! "$@"; then
    echo "::error::failed: $*" >&2
    fail=1
  fi
}

version=$(python3 -c 'import platform; print(platform.python_version())')
case "$(uname -m)" in
  x86_64) arch=x64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) echo "Unsupported architecture: $(uname -m); skipping." >&2; exit 0 ;;
esac
dest="$tmp/Python/$version/$arch"

# First run seeds a working interpreter and the completion marker.
RUNNER_DIR="$tmp/runner" RUNNER_TOOL_CACHE="$tmp" bash "$script" >"$tmp/out1"
check test -x "$dest/bin/python"
check test -f "$dest.complete"
check "$dest/bin/python" --version
# The interpreter is a copy, not a symlink to the system one.
check test ! -L "$dest/bin/python"

# A second run changes nothing and says so.
RUNNER_DIR="$tmp/runner" RUNNER_TOOL_CACHE="$tmp" bash "$script" >"$tmp/out2"
check grep -q 'already in' "$tmp/out2"

# An entry without its marker is rebuilt, not trusted.
rm "$dest.complete"
touch "$dest/stale"
RUNNER_DIR="$tmp/runner" RUNNER_TOOL_CACHE="$tmp" bash "$script" >"$tmp/out3"
check test ! -e "$dest/stale"
check test -f "$dest.complete"

exit "$fail"
