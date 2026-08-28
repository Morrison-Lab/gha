#!/usr/bin/env bash
# List the workflow files GitHub itself would discover, one path per line.
#
# Both extensions, not just `*.yml`: GitHub loads `.yml` and `.yaml` workflow
# files alike, and this repo's own detect-pr-workflow-edits.sh recognizes both
# --- so a `*.yml`-only glob lets a `.yaml` workflow bypass any audit built on
# it, silently and with nothing red (gha#705, gha#716).
#
# Top-level only (`-maxdepth 1`), for the same reason detect-pr-workflow-edits.sh
# rejects nested paths: `.github/workflows/scripts/...` is not a workflow, so an
# audit that swept it in would report findings GitHub never loads.
#
# Fails closed on an empty or missing directory rather than printing nothing.
# A caller that received no paths would run its grep over no input and pass
# having examined nothing, which is indistinguishable from a clean tree.
#
# Usage:
#   bash .github/workflows/scripts/list-workflow-files.sh [WORKFLOWS_DIR]
set -euo pipefail

dir="${1:-.github/workflows}"

if [ ! -d "$dir" ]; then
  echo "::error::list-workflow-files: workflows directory not found: $dir" >&2
  exit 1
fi

files="$(find "$dir" -maxdepth 1 -type f \( -name '*.yml' -o -name '*.yaml' \) | LC_ALL=C sort)"

if [ -z "$files" ]; then
  echo "::error::list-workflow-files: no .yml or .yaml workflow files under $dir --- an audit built on this list would pass having examined nothing." >&2
  exit 1
fi

printf '%s\n' "$files"
