#!/usr/bin/env bash
# Offline tests for scripts/wait-runner-capacity.sh's I/O limit (gha#1527):
# the job is held while procs_blocked is at or above WAIT_MAX_BLOCKED, runs at
# once when the limit is off or not reached, and still runs after the wait
# cap, so a busy host slows jobs and never fails them.
#
# Usage: bash .github/workflows/scripts/tests/run-wait-runner-capacity-tests.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
script="$repo_root/scripts/wait-runner-capacity.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0
fail() { echo "::error::$1"; failures=$((failures + 1)); }

# Memory and load limits that always pass, so only the I/O limit decides.
export WAIT_MIN_MEM_GB=0 WAIT_MAX_LOAD_PER_CORE=100000
printf 'cpu 1 1 1 1\nprocs_blocked 5\n' > "$work/busy"
printf 'cpu 1 1 1 1\nprocs_blocked 0\n' > "$work/idle"

out=$(PROC_STAT="$work/busy" bash "$script") || fail "limit off should not fail"
case "$out" in *holding*) fail "limit off should not hold: $out" ;; esac

out=$(WAIT_MAX_BLOCKED=2 PROC_STAT="$work/idle" bash "$script") || fail "idle host should not fail"
case "$out" in *holding*) fail "idle host should not hold: $out" ;; esac

out=$(WAIT_MAX_BLOCKED=2 PROC_STAT="$work/busy" WAIT_MAX_MINUTES=1 timeout 8 bash "$script")
status=$?
[ "$status" = 124 ] || fail "a host with 5 blocked processes should hold the job (exit $status): $out"

out=$(WAIT_MAX_BLOCKED=abc PROC_STAT="$work/busy" bash "$script")
case "$out" in *'::warning::'*) ;; *) fail "bad limit should warn: $out" ;; esac

# Worker limit (gha#1546): held above the cap, free at or below it, off by default.
out=$(WAIT_MAX_WORKERS=3 WAIT_WORKER_COUNT=3 bash "$script") || fail "workers at the cap should not fail"
case "$out" in *holding*) fail "workers at the cap should not hold: $out" ;; esac

out=$(WAIT_MAX_WORKERS=3 WAIT_WORKER_COUNT=8 WAIT_MAX_MINUTES=1 timeout 8 bash "$script")
status=$?
[ "$status" = 124 ] || fail "8 workers over a cap of 3 should hold the job (exit $status): $out"

out=$(WAIT_WORKER_COUNT=8 bash "$script") || fail "worker limit off should not fail"
case "$out" in *holding*) fail "worker limit off should not hold: $out" ;; esac

# A burst of held jobs drains oldest first instead of stalling (gha#1549).
# Held jobs are workers too, so two held jobs on a limit of 1 count two workers
# and no running job; the older ticket starts and the newer one waits.
export WAIT_HOLD_DIR="$work/holders"
mkdir -p "$WAIT_HOLD_DIR"
sleep 60 &
other=$!
disown "$other"
trap 'kill "$other" 2> /dev/null; rm -rf "$work"' EXIT

: > "$WAIT_HOLD_DIR/99999999999999999999-$other"
out=$(WAIT_MAX_WORKERS=1 WAIT_WORKER_COUNT=2 bash "$script") || fail "the oldest held job should not fail"
case "$out" in *holding*) fail "the oldest held job should start at once: $out" ;; esac

rm -f "$WAIT_HOLD_DIR"/*
: > "$WAIT_HOLD_DIR/00000000000000000000-$other"
out=$(WAIT_MAX_WORKERS=1 WAIT_WORKER_COUNT=2 WAIT_MAX_MINUTES=1 timeout 8 bash "$script")
status=$?
[ "$status" = 124 ] || fail "a job behind an older held job should wait (exit $status): $out"
case "$out" in *"limit of 1"*) ;; *) fail "the hold message should name the limit: $out" ;; esac

# A ticket whose process has gone is pruned, so it never holds anyone back.
rm -f "$WAIT_HOLD_DIR"/*
: > "$WAIT_HOLD_DIR/00000000000000000000-999999999"
out=$(WAIT_MAX_WORKERS=1 WAIT_WORKER_COUNT=1 bash "$script") || fail "a stale ticket should not fail"
case "$out" in *holding*) fail "a stale ticket should not hold: $out" ;; esac
[ ! -e "$WAIT_HOLD_DIR/00000000000000000000-999999999" ] || fail "a stale ticket should be pruned"

# A finished job leaves no ticket behind.
leftover=$(find "$WAIT_HOLD_DIR" -type f | wc -l)
[ "$((leftover))" = 0 ] || fail "tickets should be removed on exit ($leftover left)"

# A cancel signal ends the hold at once with success (gha#1582): the runner
# waits for the hook to exit after a job's timeout, so a held hook that ignored
# the signal kept a 5-minute job alive for 5 more minutes.
WAIT_MAX_WORKERS=1 WAIT_WORKER_COUNT=8 WAIT_MAX_MINUTES=5 bash "$script" > /dev/null &
held=$!
sleep 1
kill -TERM "$held"
for _ in 1 2 3 4 5; do
  kill -0 "$held" 2> /dev/null || break
  sleep 1
done
if kill -0 "$held" 2> /dev/null; then
  kill -KILL "$held"
  fail "a held job should stop waiting within 5 seconds of SIGTERM"
else
  wait "$held" || fail "a held job cancelled by SIGTERM should exit 0"
fi

# The default hold is shorter than the 5-minute timeout of the shortest checks.
default=$(grep -o 'WAIT_MAX_MINUTES:-[0-9]*' "$script" | head -n 1 | cut -d- -f2)
[ -n "$default" ] && [ "$default" -lt 5 ] || fail "the default WAIT_MAX_MINUTES (${default:-unset}) should be under 5"

# A busy or full host is not a defect of the code under test (gha#1584): the
# hold-expired and low-disk messages are notices, so no consumer's annotation
# gate has to allow-list them. Setup mistakes stay warnings.
grep -q '"::notice::wait-runner-capacity: still short' "$script" || fail "the hold-expired message should be a notice"
prune="$repo_root/scripts/prune-runner-workdir.sh"
grep -q '"::notice::prune-runner-workdir: measured' "$prune" || fail "the low-disk message should be a notice"
if grep -q '::warning::\(wait-runner-capacity: still short\|prune-runner-workdir: measured\)' "$script" "$prune"; then
  fail "capacity and disk messages should not be warnings"
fi

[ "$failures" = 0 ] && echo "all wait-runner-capacity tests passed"
exit "$failures"
