#!/usr/bin/env bash
# Verifies that Node.js is installed on the runner and meets the minimum required major version.
# Usage: check-node-version.sh [min_version]
# Default min_version: 18

set -euo pipefail

MIN_VERSION="${1:-18}"

if ! command -v node >/dev/null 2>&1; then
  echo "::error::Node.js is not installed on the runner. Node.js >= ${MIN_VERSION} is required." >&2
  exit 1
fi

NODE_VERSION="$(node -v 2>/dev/null || true)"
# Extract major version number (e.g., "v20.11.0" -> "20")
NODE_MAJOR="$(echo "$NODE_VERSION" | sed -E 's/^v?([0-9]+).*/\1/')"

if ! [[ "$NODE_MAJOR" =~ ^[0-9]+$ ]]; then
  echo "::error::Failed to parse Node.js version output: '$NODE_VERSION'. Node.js >= ${MIN_VERSION} is required." >&2
  exit 1
fi

if [ "$NODE_MAJOR" -lt "$MIN_VERSION" ]; then
  echo "::error::Node.js version $NODE_VERSION (major version $NODE_MAJOR) is insufficient. Node.js >= ${MIN_VERSION} is required." >&2
  exit 1
fi
