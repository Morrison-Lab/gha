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
# 4, under the 5-minute timeout of the shortest checks, gha#1582), or at once
# when the runner sends a cancel signal, then lets the job run anyway: a host that stays busy slows jobs down but
# never fails them.
# WAIT_MAX_MINUTES=0 turns the wait off.
set -uo pipefail

max_minutes="${WAIT_MAX_MINUTES:-4}"
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

# A job cancelled by its own timeout sends this hook a signal, and the runner
# then waits for the hook to exit. Stop holding at once so the cancel finishes
# (gha#1582).
trap 'exit 0' TERM INT HUP

# Held jobs are themselves Runner.Worker processes, so counting every worker
# would make a burst of held jobs keep each other held until the deadline
# (gha#1549). Each job under WAIT_MAX_WORKERS takes a ticket (a file named by
# arrival time and pid) and the count of running jobs excludes live tickets.
# A job may start when the running jobs plus the tickets ahead of it are fewer
# than the limit, so a burst drains oldest first.
hold_dir="${WAIT_HOLD_DIR:-${TMPDIR:-/tmp}/gha-wait-holders}"
ticket=""
if [ "$max_workers" -gt 0 ] && mkdir -p "$hold_dir"; then
  ticket="$hold_dir/$(date +%s%N)-$$"
  : > "$ticket"
  trap 'rm -f "$ticket"' EXIT
fi

# Prints the count of live tickets and this job's place among them (0 is
# first), pruning tickets whose process has gone.
ticket_state() {
  local f pid live=0 rank=0
  for f in "$hold_dir"/*; do
    [ -e "$f" ] || continue
    pid="${f##*-}"
    if kill -0 "$pid" 2> /dev/null; then
      [ "$f" = "$ticket" ] && rank=$live
      live=$((live + 1))
    else
      rm -f "$f"
    fi
  done
  echo "$live $rank"
}

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
  # The pattern is the worker's executable (the first word of its command line),
  # so an editor or shell whose arguments name the file does not count (gha#1551).
  workers="${WAIT_WORKER_COUNT:-$(pgrep -fc '^[^ ]*Runner[.]Worker( |$)' 2> /dev/null)}"
  running="${workers:-0}"
  if [ -n "$ticket" ]; then
    read -r holders rank <<< "$(ticket_state)"
    # Held jobs, this one included, are workers that are not running anything.
    running=$((running > holders ? running - holders : 0))
    if [ $((running + rank)) -ge "$max_workers" ]; then
      ok=0
    fi
  fi
  if [ "${mem:-0}" -ge "$min_mem_gb" ] && [ "$ok" = 1 ]; then
    break
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "::warning::wait-runner-capacity: still short after $max_minutes minutes (${mem} GB available, load $(cut -d' ' -f1 /proc/loadavg) on $cores cores, ${blocked:-0} blocked on I/O, ${running} running jobs with limit ${max_workers}); running the job anyway."
    exit 0
  fi
  if [ "$waited" = 0 ]; then
    echo "wait-runner-capacity: holding the job until at least $min_mem_gb GB is available and load is under $max_load_per_core per core (now ${mem} GB, load $(cut -d' ' -f1 /proc/loadavg) on $cores cores, ${running} running jobs against a limit of ${max_workers}, where 0 means no limit)."
    waited=1
  fi
  # A foreground sleep would delay the signal trap until the sleep ended.
  sleep 15 &
  wait $!
done
exit 0
