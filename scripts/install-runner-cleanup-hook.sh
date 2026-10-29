#!/usr/bin/env bash
# Point a self-hosted runner's job-completed hook at
# scripts/prune-runner-workdir.sh, so old checkouts are removed after each job
# (gha#1352). The listener reads ACTIONS_RUNNER_HOOK_JOB_COMPLETED from .env
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
if [ -f "$env_file" ] && grep -q '^ACTIONS_RUNNER_HOOK_JOB_COMPLETED=' "$env_file"; then
  echo "$env_file already sets a job-completed hook; kept it."
  exit 0
fi
# .env may lack a final newline; start the line on its own line.
if [ -s "$env_file" ] && [ -n "$(tail -c 1 "$env_file")" ]; then
  echo >> "$env_file"
fi
echo "ACTIONS_RUNNER_HOOK_JOB_COMPLETED=$hook" >> "$env_file"
echo "Set the runner's job-completed hook to $hook in $env_file."
