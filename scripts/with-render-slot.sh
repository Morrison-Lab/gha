#!/usr/bin/env bash
# check-one-function-per-file: allow-multiple
# Hold one of a few per-host "render slots" while a heavy local render runs,
# so a burst of Quarto renders on one self-hosted host queues instead of
# filling its memory and swap (gha#2062).
#
# The job-started hook (wait-runner-capacity.sh) cannot do this job. It runs
# before any step, so it cannot tell a render from a 5-minute lint check, and
# its hold counts against the job's timeout-minutes, so it has to give up after
# a couple of minutes and run the job anyway (gha#1718). On 2026-11-16 that let
# eleven jobs onto cf463-02 at once, most of them renders, and the 16-core,
# 15 GB host thrashed at a load of about 105. The lock here is taken at the
# render itself, inside jobs whose timeouts are long, so it waits as long as
# it has to: the render is the only thing that waits, and only for another
# render.
#
# Usage, as a wrapper:   bash scripts/with-render-slot.sh COMMAND [ARGS...]
# Usage, in a shell:     source scripts/with-render-slot.sh && acquire_render_slot
#   Sourced, it defines acquire_render_slot, which takes a slot on file
#   descriptor 9 of the calling shell; the slot is held until that shell exits.
#
# A slot is a flock on one of N files in RENDER_SLOT_DIR. The kernel drops the
# lock when the holder exits, however it exits, so a killed render leaves no
# stale slot behind, which is why this is not a ticket file.
#
# Environment:
#   RENDER_SLOTS              slots on this host (default: MemTotal divided by
#                             RENDER_GB_PER_SLOT, rounded down, at least 1)
#   RENDER_GB_PER_SLOT        GB of memory one render may use (default 4; a
#                             Quarto site render peaks near 3 GB, gha#1509)
#   RENDER_SLOT_DIR           lock directory (default /tmp/gha-render-slots).
#                             Keep it on a local disk: the home directory is
#                             NFS shared by both lab hosts, and a slot is
#                             per host.
#   RENDER_SLOT_WAIT_MINUTES  longest wait, then run anyway with a notice
#                             (default 0: wait until a slot frees or the job's
#                             own timeout cancels it)
# A GitHub-hosted runner (RUNNER_ENVIRONMENT=github-hosted) runs one job per
# machine, so it skips the slot, as does a host without flock.
# MEMINFO stands in for /proc/meminfo in the tests.

acquire_render_slot() {
  if [ "${RUNNER_ENVIRONMENT:-}" = github-hosted ]; then
    return 0
  fi
  if ! command -v flock > /dev/null 2>&1; then
    echo "::warning::with-render-slot: flock not found; rendering without a slot."
    return 0
  fi
  local slots="${RENDER_SLOTS:-}" gb="${RENDER_GB_PER_SLOT:-4}"
  local dir="${RENDER_SLOT_DIR:-/tmp/gha-render-slots}"
  local max_minutes="${RENDER_SLOT_WAIT_MINUTES:-0}"
  local meminfo="${MEMINFO:-/proc/meminfo}"
  case "$gb$max_minutes" in
    '' | *[!0-9]*)
      echo "::warning::with-render-slot: RENDER_GB_PER_SLOT and RENDER_SLOT_WAIT_MINUTES must be whole numbers; rendering without a slot."
      return 0
      ;;
  esac
  if [ -z "$slots" ]; then
    [ "$gb" -gt 0 ] || gb=4
    slots=$(awk -v g="$gb" '/^MemTotal:/ { n = int($2 / 1048576 / g); print (n < 1) ? 1 : n }' "$meminfo")
  fi
  case "$slots" in
    '' | *[!0-9]* | 0)
      echo "::warning::with-render-slot: no usable slot count ('$slots'); rendering without a slot."
      return 0
      ;;
  esac
  if ! mkdir -p "$dir"; then
    echo "::warning::with-render-slot: cannot create $dir; rendering without a slot."
    return 0
  fi

  local start=$SECONDS waited=0 i
  while :; do
    for ((i = 1; i <= slots; i++)); do
      exec 9>> "$dir/slot-$i"
      if flock -n 9; then
        echo "with-render-slot: rendering in slot $i of $slots on $(hostname)$([ "$waited" = 1 ] && echo " after $(((SECONDS - start) / 60)) min $(((SECONDS - start) % 60)) s")."
        return 0
      fi
      exec 9>&-
    done
    if [ "$max_minutes" -gt 0 ] && [ $((SECONDS - start)) -ge $((max_minutes * 60)) ]; then
      echo "::notice::with-render-slot: all $slots render slots on $(hostname) still busy after $max_minutes minutes; rendering anyway."
      return 0
    fi
    if [ "$waited" = 0 ]; then
      echo "with-render-slot: all $slots render slots on $(hostname) are busy; waiting for one to free (checking every 15 s)."
      waited=1
    fi
    # A foreground sleep would delay a cancel's signal until it ended.
    sleep 15 &
    wait $!
  done
}

# Run as a script: take a slot, then become the command, which keeps the lock.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -uo pipefail
  if [ "$#" -eq 0 ]; then
    echo "usage: $0 COMMAND [ARGS...]" >&2
    exit 2
  fi
  trap 'exit 143' TERM
  trap 'exit 130' INT
  acquire_render_slot
  trap - TERM INT
  exec "$@"
fi
