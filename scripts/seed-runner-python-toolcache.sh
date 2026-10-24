#!/usr/bin/env bash
# check-one-function-per-file: allow-multiple
# Put the system Python into a self-hosted runner's toolcache, so
# actions/setup-python finds it. On a distribution it publishes no build for
# (Debian 13 as of 2026-10-23), setup-python otherwise fails with
# "The version '3.x' with architecture 'x64' was not found" (gha#1205).
#
# Usage: RUNNER_DIR=<runner directory> bash scripts/seed-runner-python-toolcache.sh
#
# The entry is a copied virtual environment (`venv --copies`), so the
# interpreter binary is a copy, not a symlink. It still imports the system
# Python's standard library, so run this script again after the system Python
# changes: a new patch version gets its own entry, and the old entry may break.
# Idempotent.
set -euo pipefail

RUNNER_DIR="$(realpath -m "${RUNNER_DIR:-$HOME/actions-runner-private}")"
TOOL_CACHE="${RUNNER_TOOL_CACHE:-$RUNNER_DIR/_work/_tool}"

if ! python3 -c 'import venv, ensurepip' >/dev/null; then
  echo "python3 with the venv module is required (Debian: apt install python3-venv)." >&2
  exit 1
fi

version=$(python3 -c 'import platform; print(platform.python_version())')
case "$(uname -m)" in
  x86_64) arch=x64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

dest="$TOOL_CACHE/Python/$version/$arch"
if [ -f "$dest.complete" ]; then
  echo "Python $version already in $TOOL_CACHE."
  exit 0
fi

rm -rf "$dest"
mkdir -p "$dest"
python3 -m venv --copies "$dest"
"$dest/bin/python" --version
touch "$dest.complete"
echo "Seeded $dest."
