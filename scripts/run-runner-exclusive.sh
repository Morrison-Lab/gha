#!/usr/bin/env bash
# Start a self-hosted runner's ./run.sh unless a listener for that runner
# directory is already running, so one registration never gets two listeners
# (gha#1370). Two listeners loop on "A session for this runner already exists"
# and compete for jobs; on 2026-10-30 a second `nohup ./run.sh`, started 7 s
# after the first, did exactly that on private-cf463-01-3.
#
# Usage: RUNNER_DIR=<runner directory> bash scripts/run-runner-exclusive.sh
#
# Two guards, because a check alone races and a lock alone misses a listener
# started without it:
#   1. A lock on <runner directory>/.listener.lock, held by this script for as
#      long as run.sh runs. A second start while it is held refuses at once.
#   2. A scan for a Runner.Listener already running from this directory on this
#      host, started some other way (a bare `nohup ./run.sh`). It names the PID.
# Either refusal exits 75 (EX_TEMPFAIL) and starts nothing.
#
# The script stays in the foreground as run.sh's parent and passes SIGTERM and
# SIGINT on to it, so systemd (scripts/gha-runner@.service) still stops the
# runner gracefully. run.sh gets the lock's descriptor closed, so a job's
# leftover background process cannot keep the lock after the runner stops.
set -euo pipefail

RUNNER_DIR="${RUNNER_DIR:?set RUNNER_DIR to the runner directory}"
cd "$RUNNER_DIR"
if [ ! -x ./run.sh ]; then
  echo "No run.sh in $RUNNER_DIR." >&2
  exit 1
fi
# The listener's command line holds the physical path. Compare it as a string,
# since a directory name may hold characters a pgrep -f pattern would misread.
physical_dir=$(pwd -P)

exec 9> .listener.lock
if ! flock -n 9; then
  echo "Another start of $physical_dir holds .listener.lock; not starting a second listener." >&2
  exit 75
fi

listeners=""
for pid in $(pgrep -x Runner.Listener || true); do
  if [ "$(tr '\0' '\n' < "/proc/$pid/cmdline" 2> /dev/null | head -n 1)" \
    = "$physical_dir/bin/Runner.Listener" ]; then
    listeners="$listeners $pid"
  fi
done
if [ -n "$listeners" ]; then
  echo "A listener for $physical_dir is already running (PID:$listeners);" \
    "not starting a second one. Stop it between jobs first." >&2
  exit 75
fi

./run.sh "$@" 9>&- &
child=$!
trap 'kill -TERM "$child" 2> /dev/null || true' TERM INT
# wait returns early when a trapped signal arrives, so wait until run.sh exits.
status=0
wait "$child" || status=$?
while kill -0 "$child" 2> /dev/null; do
  status=0
  wait "$child" || status=$?
done
exit "$status"
