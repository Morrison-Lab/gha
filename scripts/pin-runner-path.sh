#!/usr/bin/env bash
# Copy a self-hosted runner's PATH from its .path file into its .env file, so
# the listener and its jobs keep the PATH however the runner is started
# (gha#1341). config.sh records the configuring shell's PATH in .path, but
# only svc.sh's runsvc.sh reads that file; `nohup ./run.sh`, which
# scripts/register-self-hosted-runner.sh uses, passes on the caller's PATH
# instead. The listener loads .env at startup in both cases.
#
# Usage: RUNNER_DIR=<runner directory> bash scripts/pin-runner-path.sh
#
# Adds a PATH= line only when .env has none, so a PATH set there by hand is
# kept; delete that line to pin again from .path. Takes effect when the
# runner next starts. Idempotent.
set -euo pipefail

RUNNER_DIR="${RUNNER_DIR:?set RUNNER_DIR to the runner directory}"
path_file="$RUNNER_DIR/.path"
env_file="$RUNNER_DIR/.env"

# An empty PATH= line would make the listener unset PATH, which is worse than
# the PATH it is started with, so a blank first line is an error too.
path=""
if [ -f "$path_file" ]; then
  path=$(head -n 1 "$path_file")
fi
if [ -z "$path" ]; then
  echo "No PATH recorded in $path_file." >&2
  exit 1
fi
if [ -f "$env_file" ] && grep -q '^PATH=' "$env_file"; then
  echo "$env_file already sets PATH; kept it."
  exit 0
fi
# .env may lack a final newline; start the PATH line on its own line.
if [ -s "$env_file" ] && [ -n "$(tail -c 1 "$env_file")" ]; then
  echo >> "$env_file"
fi
echo "PATH=$path" >> "$env_file"
echo "Pinned the runner's PATH in $env_file."
