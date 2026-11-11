#!/usr/bin/env bash
# Offline tests for scripts/run-runner-exclusive.sh (gha#1370): it starts
# run.sh when nothing else runs the runner, refuses while another start holds
# the lock, refuses while a listener started some other way is running from the
# same directory, ignores a listener from a different directory, passes
# run.sh's exit status through, and forwards SIGTERM to run.sh.
#
# Usage: bash .github/workflows/scripts/tests/run-run-runner-exclusive-tests.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
script="$repo_root/scripts/run-runner-exclusive.sh"
work=$(mktemp -d)
pids=()
# shellcheck disable=SC2329 # invoked by the EXIT trap
cleanup() {
  for pid in "${pids[@]}"; do kill -KILL "$pid" 2> /dev/null || true; done
  rm -rf "$work"
}
trap cleanup EXIT
failures=0
fail() { echo "::error::$1"; failures=$((failures + 1)); }

# make_runner <dir> <run.sh body>: a fake runner directory. The listener is a
# copy of sleep named Runner.Listener, so pgrep -x and its argv[0] match the
# real one's.
make_runner() {
  mkdir -p "$1/bin"
  cp "$(command -v sleep)" "$1/bin/Runner.Listener"
  printf '#!/usr/bin/env bash\n%s\n' "$2" > "$1/run.sh"
  chmod +x "$1/run.sh"
}

# A free runner starts run.sh, and the exit status comes back.
make_runner "$work/a" 'echo started > ran; exit 3'
RUNNER_DIR="$work/a" bash "$script" > /dev/null 2>&1
status=$?
[ "$status" = 3 ] || fail "run.sh's exit status should pass through, got $status"
[ -f "$work/a/ran" ] || fail "a free runner should start run.sh"

# While another start holds the lock, a second start refuses with 75.
make_runner "$work/b" 'echo started >> ran; sleep 30'
RUNNER_DIR="$work/b" bash "$script" > /dev/null 2>&1 &
pids+=($!)
for _ in $(seq 50); do [ -f "$work/b/ran" ] && break; sleep 0.1; done
out=$(RUNNER_DIR="$work/b" bash "$script" 2>&1)
status=$?
[ "$status" = 75 ] || fail "a start while the lock is held should exit 75, got $status"
case "$out" in *".listener.lock"*) ;; *) fail "the refusal should name the lock: $out" ;; esac
[ "$(wc -l < "$work/b/ran")" = 1 ] || fail "a refused start should not run run.sh"

# A listener started without the wrapper is found by its path, and named.
make_runner "$work/c" 'echo started > ran'
(cd "$work/c" && exec "$(pwd -P)/bin/Runner.Listener" 30) &
listener=$!
pids+=("$listener")
sleep 0.3
out=$(RUNNER_DIR="$work/c" bash "$script" 2>&1)
status=$?
[ "$status" = 75 ] || fail "a running listener should make the start exit 75, got $status"
case "$out" in *"$listener"*) ;; *) fail "the refusal should name PID $listener: $out" ;; esac
[ ! -f "$work/c/ran" ] || fail "a start beside a running listener should not run run.sh"

# A listener from another runner directory does not block this one.
make_runner "$work/d" 'echo started > ran'
RUNNER_DIR="$work/d" bash "$script" > /dev/null 2>&1 ||
  fail "another directory's listener should not block a start"
[ -f "$work/d/ran" ] || fail "another directory's listener should not stop run.sh"

# SIGTERM to the wrapper reaches run.sh, which exits through its own trap.
make_runner "$work/e" 'trap "echo stopped > stopped; exit 0" TERM; echo started > ran; while :; do sleep 0.1; done'
RUNNER_DIR="$work/e" bash "$script" > /dev/null 2>&1 &
wrapper=$!
pids+=("$wrapper")
for _ in $(seq 50); do [ -f "$work/e/ran" ] && break; sleep 0.1; done
kill -TERM "$wrapper"
for _ in $(seq 50); do kill -0 "$wrapper" 2> /dev/null || break; sleep 0.1; done
kill -0 "$wrapper" 2> /dev/null && fail "the wrapper should exit after SIGTERM"
[ -f "$work/e/stopped" ] || fail "SIGTERM should reach run.sh"

# The lock is released once run.sh exits, so the next start succeeds.
rm -f "$work/e/ran"
make_runner "$work/e" 'echo started > ran'
RUNNER_DIR="$work/e" bash "$script" > /dev/null 2>&1 ||
  fail "a start after the runner stopped should succeed"
[ -f "$work/e/ran" ] || fail "a start after the runner stopped should run run.sh"

[ "$failures" = 0 ] && echo "all run-runner-exclusive tests passed"
exit "$failures"
