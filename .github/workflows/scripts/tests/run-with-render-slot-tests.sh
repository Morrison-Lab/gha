#!/usr/bin/env bash
# Offline tests for scripts/with-render-slot.sh (gha#2062): a render takes a
# free slot at once, waits while every slot is held, takes the slot as soon as
# its holder exits, derives the slot count from memory, and is skipped on a
# GitHub-hosted runner.
#
# Usage: bash .github/workflows/scripts/tests/run-with-render-slot-tests.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
script="$repo_root/scripts/with-render-slot.sh"
work=$(mktemp -d)
holders=()
cleanup() {
  for pid in "${holders[@]}"; do kill "$pid" 2> /dev/null; done
  rm -rf "$work"
}
trap cleanup EXIT
failures=0
fail() { echo "::error::$1"; failures=$((failures + 1)); }

export RUNNER_ENVIRONMENT=self-hosted RENDER_SLOT_DIR="$work/slots"

# A free slot runs the command at once and passes its exit status through.
out=$(RENDER_SLOTS=2 bash "$script" bash -c 'echo ran; exit 3')
status=$?
[ "$status" = 3 ] || fail "the command's exit status should pass through (got $status)"
case "$out" in *'slot 1 of 2'*ran*) ;; *) fail "a free slot should run at once: $out" ;; esac

# Hold both slots with long-running wrapped commands.
RENDER_SLOTS=2 bash "$script" sleep 60 > /dev/null &
holders+=($!)
RENDER_SLOTS=2 bash "$script" sleep 60 > /dev/null &
holders+=($!)
sleep 1

# Every slot held: the render waits (timeout kills it while it waits).
out=$(RENDER_SLOTS=2 timeout 4 bash "$script" echo ran)
status=$?
[ "$status" = 124 ] || fail "with every slot held the render should wait (exit $status): $out"
case "$out" in *busy*) ;; *) fail "a waiting render should say the slots are busy: $out" ;; esac
case "$out" in *ran*) fail "a waiting render should not run: $out" ;; esac

# A third slot is free, so the same render runs at once.
out=$(RENDER_SLOTS=3 bash "$script" echo ran)
case "$out" in *'slot 3 of 3'*ran*) ;; *) fail "the free third slot should be used: $out" ;; esac

# The wait cap, when set, runs the render anyway with a notice.
out=$(RENDER_SLOTS=2 RENDER_SLOT_WAIT_MINUTES=1 timeout 4 bash "$script" echo ran)
[ $? = 124 ] || fail "a 1-minute cap should still be waiting after 4 s: $out"

# When a holder exits, its slot frees and a waiting render takes it.
RENDER_SLOTS=2 bash "$script" echo ran > "$work/waiter.out" &
waiter=$!
sleep 1
# The wrapper execs the command, so the holder's pid is the sleep itself.
kill "${holders[0]}"
waited=0
while kill -0 "$waiter" 2> /dev/null && [ "$waited" -lt 30 ]; do
  sleep 1
  waited=$((waited + 1))
done
if kill -0 "$waiter" 2> /dev/null; then
  kill "$waiter"
  fail "a waiting render should start once a slot frees: $(cat "$work/waiter.out")"
else
  case "$(cat "$work/waiter.out")" in *'after '*ran*) ;; *) fail "the freed slot should be taken after a wait: $(cat "$work/waiter.out")" ;; esac
fi

# Slot count from memory: 15 GB at 4 GB a slot is 3 slots; tiny hosts get 1.
printf 'MemTotal:       15728640 kB\n' > "$work/meminfo15"
printf 'MemTotal:        2097152 kB\n' > "$work/meminfo2"
out=$(RENDER_SLOT_DIR="$work/mem" MEMINFO="$work/meminfo15" bash "$script" true)
case "$out" in *'of 3 '*) ;; *) fail "15 GB at 4 GB a slot should give 3 slots: $out" ;; esac
out=$(RENDER_SLOT_DIR="$work/mem" MEMINFO="$work/meminfo2" bash "$script" true)
case "$out" in *'of 1 '*) ;; *) fail "a 2 GB host should still get 1 slot: $out" ;; esac

# A GitHub-hosted runner skips the slot entirely.
out=$(RUNNER_ENVIRONMENT=github-hosted RENDER_SLOTS=abc bash "$script" echo ran)
[ "$out" = ran ] || fail "a GitHub-hosted runner should run with no slot: $out"

# A bad setting warns and runs rather than failing the render.
out=$(RENDER_GB_PER_SLOT=x bash "$script" echo ran)
case "$out" in *'::warning::'*ran*) ;; *) fail "a bad setting should warn and run: $out" ;; esac

# Sourced, acquire_render_slot holds the slot for the calling shell's life.
out=$(RENDER_SLOTS=1 RENDER_SLOT_DIR="$work/src" bash -c "source '$script' && acquire_render_slot && RENDER_SLOTS=1 RENDER_SLOT_DIR='$work/src' timeout 3 bash '$script' echo inner")
case "$out" in *'slot 1 of 1'*busy*) ;; *) fail "a sourced slot should block a second render until the shell exits: $out" ;; esac
case "$out" in *inner*) fail "the inner render should not run while the sourced slot is held: $out" ;; esac

if [ "$failures" -gt 0 ]; then
  echo "$failures with-render-slot test(s) failed."
  exit 1
fi
echo "All with-render-slot tests passed."
