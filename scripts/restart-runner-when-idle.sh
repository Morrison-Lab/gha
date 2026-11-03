#!/usr/bin/env bash
# Restart a self-hosted runner between jobs, so it reloads its .env and .path
# (for example after scripts/pin-runner-path.sh, or after adding a tool's
# directory to PATH). The listener reads both only when it starts.
#
# Usage: RUNNER_DIR=<runner directory> bash scripts/restart-runner-when-idle.sh
#
# Waits until the runner's listener has had no Runner.Worker child for
# IDLE_SECONDS (default 10), then stops it with SIGTERM. A listener started by `setsid nohup ./run.sh` ignores SIGINT:
# `pkill -INT` left the old listener running, and the relaunch became a second
# listener that looped on "A session for this runner already exists"
# (2026-11-02). Relaunches only after the old listener has exited. Run it in the
# background (setsid nohup ... &) to leave it waiting for a long job.
set -euo pipefail

RUNNER_DIR="${RUNNER_DIR:?set RUNNER_DIR to the runner directory}"
cd "$RUNNER_DIR"
# Two copies of this script on one runner would both relaunch it.
exec 9> .restart-when-idle.lock
if ! flock -n 9; then
  echo "A restart of $RUNNER_DIR is already waiting." >&2
  exit 1
fi
# The listener's command line holds the physical path. Compare it as a string,
# since a directory name may hold characters a pgrep -f pattern would misread.
physical_dir=$(pwd -P)
find_listeners() {
  local pid
  for pid in $(pgrep -x Runner.Listener || true); do
    if [ "$(tr '\0' '\n' < "/proc/$pid/cmdline" 2> /dev/null | head -n 1)" \
      = "$physical_dir/bin/Runner.Listener" ]; then
      echo "$pid"
    fi
  done
}

listeners=$(find_listeners)
if [ "$(echo "$listeners" | wc -w)" != 1 ]; then
  echo "Expected one listener in $physical_dir, found: ${listeners:-none}." >&2
  exit 1
fi
listener=$listeners

# Read the PATH before stopping anything: an empty one would make the relaunch
# fail after the listener is gone.
runner_path=""
if [ -f .path ]; then
  runner_path=$(head -n 1 .path)
fi
if [ -z "$runner_path" ]; then
  echo "No PATH recorded in $RUNNER_DIR/.path; not restarting." >&2
  exit 1
fi

# The listener reports a job's result after its worker exits, and accepts the
# next job before it starts a worker, so require IDLE_SECONDS with no worker.
# That narrows the gap in which a job can be cut off; it cannot close it.
idle_seconds=${IDLE_SECONDS:-10}
if ! [ "$idle_seconds" -ge 1 ] 2> /dev/null; then
  echo "IDLE_SECONDS must be a whole number of seconds, at least 1." >&2
  exit 1
fi
idle=0
while [ "$idle" -lt "$idle_seconds" ]; do
  if pgrep -P "$listener" -f Runner.Worker > /dev/null; then idle=0; else idle=$((idle + 1)); fi
  sleep 1
done
# The listener may have exited on its own meanwhile; relaunch either way.
kill -TERM "$listener" 2> /dev/null || true
for _ in $(seq 120); do
  kill -0 "$listener" 2> /dev/null || break
  sleep 1
done
if kill -0 "$listener" 2> /dev/null; then
  echo "Listener $listener is still running two minutes after SIGTERM;" \
    "not starting another. Start the runner by hand once it exits." >&2
  exit 1
fi

# Close the lock's descriptor in the new runner, or it would hold the lock.
PATH="$runner_path" setsid nohup ./run.sh >> runner.log 2>&1 < /dev/null 9>&- &
# run.sh starts the listener through run-helper.sh, so give it a moment.
for _ in $(seq 30); do
  if [ -n "$(find_listeners)" ]; then
    echo "Runner restarted (log: $RUNNER_DIR/runner.log)."
    exit 0
  fi
  sleep 1
done
echo "No listener came up within 30 seconds; run.sh may still be starting." \
  "Read $RUNNER_DIR/runner.log before starting it again." >&2
exit 1
