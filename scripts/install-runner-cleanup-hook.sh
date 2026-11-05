#!/usr/bin/env bash
# Point a self-hosted runner's job-completed hook at
# scripts/prune-runner-workdir.sh, so old checkouts are removed after each job
# (gha#1352), and its job-started hook at scripts/check-runner-disk.sh,
# so a job fails early when the disk is short (gha#1495). The listener reads ACTIONS_RUNNER_HOOK_JOB_COMPLETED from .env
# when it starts, so this takes effect at the runner's next start.
#
# Usage: RUNNER_DIR=<runner directory> bash scripts/install-runner-cleanup-hook.sh
#
# Adds the line only when .env sets no job-completed hook, so a hook set there
# by hand is kept. Idempotent.
set -euo pipefail

RUNNER_DIR="${RUNNER_DIR:?set RUNNER_DIR to the runner directory}"
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
hook="$SCRIPT_DIR/prune-runner-workdir.sh"
env_file="$RUNNER_DIR/.env"

if [ ! -f "$hook" ]; then
  echo "No hook script at $hook." >&2
  exit 1
fi
# set_hook <variable> <script> <label>: add the line unless .env already sets it.
set_hook() {
  if [ -f "$env_file" ] && grep -q "^$1=" "$env_file"; then
    echo "$env_file already sets a $3 hook; kept it."
    return
  fi
  # .env may lack a final newline; start the line on its own line.
  if [ -s "$env_file" ] && [ -n "$(tail -c 1 "$env_file")" ]; then
    echo >> "$env_file"
  fi
  echo "$1=$2" >> "$env_file"
  echo "Set the runner's $3 hook to $2 in $env_file."
}

set_hook ACTIONS_RUNNER_HOOK_JOB_COMPLETED "$hook" job-completed
# The job-started hook fails a job early when the disk is short (gha#1495).
set_hook ACTIONS_RUNNER_HOOK_JOB_STARTED "$SCRIPT_DIR/check-runner-disk.sh" job-started
