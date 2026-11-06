#!/usr/bin/env bash
# Job-started step for a self-hosted runner: hold a new job at its start until
# the host has memory and CPU to spare, so a burst of simultaneous jobs queues
# on the host instead of pushing it into swap (gha#1509).
#
# scripts/check-runner-disk.sh calls this after its disk check passes.
# It waits until both hold:
#   - MemAvailable is at least WAIT_MIN_MEM_GB (default 3), and
#   - the 1-minute load average is under WAIT_MAX_LOAD_PER_CORE (default 1.25)
#     times the number of cores.
# A third limit is off by default: WAIT_MAX_BLOCKED, when above 0, also waits
# until fewer than that many processes are blocked on disk I/O (procs_blocked
# in /proc/stat). A host with a slow disk, such as a spinning drive under
# several Quarto renders, can show a low load average while jobs stall on
# writes, so load alone does not hold the next job back (gha#1527).
# A fourth limit is off by default: WAIT_MAX_WORKERS, when above 0, also waits
# until no more than that many Runner.Worker processes are running on the host
# (the job's own worker counts). A Quarto render takes minutes to grow to its
# full memory, so jobs that start close together all pass the memory check and
# the host runs out of memory later (gha#1546).
# It polls every 15 seconds and stops waiting after WAIT_MAX_MINUTES (default
# 10), then lets the job run anyway: a host that stays busy slows jobs down but
# never fails them.
# WAIT_MAX_MINUTES=0 turns the wait off.
set -uo pipefail

max_minutes="${WAIT_MAX_MINUTES:-10}"
min_mem_gb="${WAIT_MIN_MEM_GB:-3}"
max_load_per_core="${WAIT_MAX_LOAD_PER_CORE:-1.25}"
max_blocked="${WAIT_MAX_BLOCKED:-0}"
max_workers="${WAIT_MAX_WORKERS:-0}"
proc_stat="${PROC_STAT:-/proc/stat}"

case "$max_minutes$min_mem_gb$max_blocked$max_workers" in
  '' | *[!0-9]*) echo "::warning::wait-runner-capacity: WAIT_MAX_MINUTES, WAIT_MIN_MEM_GB, WAIT_MAX_BLOCKED and WAIT_MAX_WORKERS must be whole numbers; not waiting."; exit 0 ;;
esac
[ "$max_minutes" -gt 0 ] || exit 0

cores=$(nproc)

deadline=$((SECONDS + max_minutes * 60))
waited=0
while :; do
  mem=$(awk '/^MemAvailable:/ { print int($2 / 1048576) }' /proc/meminfo)
  # ok is 1 when the load average is under the cap, otherwise 0.
  ok=$(awk -v cap="$max_load_per_core" -v cores="$cores" '{ print ($1 < cap * cores) ? 1 : 0 }' /proc/loadavg)
  blocked=$(awk '/^procs_blocked / { print $2 }' "$proc_stat" 2> /dev/null)
  if [ "$max_blocked" -gt 0 ] && [ "${blocked:-0}" -ge "$max_blocked" ]; then
    ok=0
  fi
  # WAIT_WORKER_COUNT lets the tests stand in for the live process count.
  workers="${WAIT_WORKER_COUNT:-$(pgrep -fc 'Runner.Worker' 2> /dev/null)}"
  if [ "$max_workers" -gt 0 ] && [ "${workers:-0}" -gt "$max_workers" ]; then
    ok=0
  fi
  if [ "${mem:-0}" -ge "$min_mem_gb" ] && [ "$ok" = 1 ]; then
    break
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "::warning::wait-runner-capacity: still short after $max_minutes minutes (${mem} GB available, load $(cut -d' ' -f1 /proc/loadavg) on $cores cores, ${blocked:-0} blocked on I/O, ${workers:-0} runner workers); running the job anyway."
    exit 0
  fi
  if [ "$waited" = 0 ]; then
    echo "wait-runner-capacity: holding the job until at least $min_mem_gb GB is available and load is under $max_load_per_core per core (now ${mem} GB, load $(cut -d' ' -f1 /proc/loadavg) on $cores cores)."
    waited=1
  fi
  sleep 15
done
exit 0
