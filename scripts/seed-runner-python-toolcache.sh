#!/usr/bin/env bash
# Put the system Python into a self-hosted runner's toolcache, so
# actions/setup-python finds it. On a distribution it publishes no build for
# (Debian 13 as of 2026-10-23), setup-python otherwise fails with
# "The version '3.x' with architecture 'x64' was not found" (gha#1205).
#
# Usage: RUNNER_DIR=<runner directory> bash scripts/seed-runner-python-toolcache.sh
#
# The entry is a copied virtual environment, not symlinks, so it survives a
# later system Python upgrade until the script is run again. Idempotent.
# Run it again after the system Python's version changes.
set -euo pipefail

RUNNER_DIR="$(realpath -m "${RUNNER_DIR:-$HOME/actions-runner-private}")"
TOOL_CACHE="${RUNNER_TOOL_CACHE:-$RUNNER_DIR/_work/_tool}"

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
