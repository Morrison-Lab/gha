#!/usr/bin/env bash
# Tests for scripts/with-r-install-lock.sh (gha#1311, gha#1409):
# stale 00LOCK* are removed, fresh ones kept, and concurrent runs never overlap.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
script="$root/scripts/with-r-install-lock.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

export R_INSTALL_LOCK_FILE="$tmp/lock"
export R_INSTALL_LIB_DIRS="$tmp/lib"
mkdir -p "$tmp/lib/00LOCK-old" "$tmp/lib/00LOCK-new" "$tmp/lib/keep"
touch -d '2 hours ago' "$tmp/lib/00LOCK-old"

bash "$script" true
[ ! -e "$tmp/lib/00LOCK-old" ] || { echo "FAIL: stale lock kept"; exit 1; }
[ -d "$tmp/lib/00LOCK-new" ] || { echo "FAIL: fresh lock removed"; exit 1; }
[ -d "$tmp/lib/keep" ] || { echo "FAIL: unrelated directory removed"; exit 1; }

# The command's exit status passes through.
if bash "$script" false; then echo "FAIL: exit status lost"; exit 1; fi

# Concurrent runs are serialized: no two critical sections overlap.
log="$tmp/log"
: >"$log"
for i in 1 2 3 4; do
  bash "$script" bash -c "echo start >>'$log'; sleep 0.3; echo end >>'$log'" &
done
wait
expected=$(printf 'start\nend\n%.0s' 1 2 3 4)
[ "$(cat "$log")" = "$expected" ] || { echo "FAIL: runs overlapped"; cat "$log"; exit 1; }

# A wait past the timeout fails instead of hanging.
exec 8>"$R_INSTALL_LOCK_FILE"
flock 8
if R_INSTALL_LOCK_TIMEOUT=1 bash "$script" true; then echo "FAIL: no timeout"; exit 1; fi
echo "with-r-install-lock tests passed"
