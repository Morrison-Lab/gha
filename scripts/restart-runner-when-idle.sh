#!/usr/bin/env bash
# Restart a self-hosted runner between jobs, so it reloads its .env and .path
# (for example after scripts/pin-runner-path.sh, or after adding a tool's
# directory to PATH). The listener reads both only when it starts.
#
# Usage: RUNNER_DIR=<runner directory> bash scripts/restart-runner-when-idle.sh
#
# Waits until the runner's listener has no Runner.Worker child, then stops it
# with SIGTERM. A listener started by `setsid nohup ./run.sh` ignores SIGINT:
# `pkill -INT` left the old listener running, and the relaunch became a second
# listener that looped on "A session for this runner already exists"
# (2026-11-02). Relaunches only after the old listener has exited. Run it in the
# background (setsid nohup ... &) to leave it waiting for a long job.
set -euo pipefail

RUNNER_DIR="${RUNNER_DIR:?set RUNNER_DIR to the runner directory}"
cd "$RUNNER_DIR"
# The listener's command line holds the physical path.
physical_dir=$(pwd -P)

listeners=$(pgrep -f "^${physical_dir}/bin/Runner.Listener" || true)
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

has_worker() { pgrep -P "$listener" -f Runner.Worker > /dev/null; }

# Check twice, a second apart, to narrow the gap in which a job can start.
while :; do
  while has_worker; do sleep 1; done
  sleep 1
  has_worker || break
done
kill -TERM "$listener"
for _ in $(seq 30); do
  kill -0 "$listener" 2> /dev/null || break
  sleep 1
done
if kill -0 "$listener" 2> /dev/null; then
  echo "Listener $listener is still running; not starting another." >&2
  exit 1
fi

PATH="$runner_path" setsid nohup ./run.sh >> runner.log 2>&1 < /dev/null &
# run.sh starts the listener through run-helper.sh, so give it a moment.
for _ in $(seq 30); do
  if pgrep -f "^${physical_dir}/bin/Runner.Listener" > /dev/null; then
    echo "Runner restarted (log: $RUNNER_DIR/runner.log)."
    exit 0
  fi
  sleep 1
done
echo "No listener came up within 30 seconds; see $RUNNER_DIR/runner.log." >&2
exit 1
