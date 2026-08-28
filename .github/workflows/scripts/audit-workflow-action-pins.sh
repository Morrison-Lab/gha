#!/usr/bin/env bash
# Fail when any workflow references a third-party action that is not pinned to
# a full 40-character commit SHA (gha#328).
#
# Exempt, in the order the filters apply:
#   - local refs (`uses: ./...`), which are this repo's own composites;
#   - `Morrison-Lab/gha` refs, which are this repo calling itself at a tag.
#
# Lives in a script rather than inline in `_selftest.yml` so the grep's exit
# status can be read three ways rather than two, and so the whole audit is
# testable offline against fixtures that carry the violation (gha#716).
#
# **What this does not cover (gha#720).** The anchor is a line-leading `uses:`,
# so only the continuation form is examined:
#
#     - name: Check out
#       uses: actions/checkout@<sha>
#
# The list-item form `- uses: actions/checkout@<sha>` is not, and this repo uses
# it widely --- five action references are exempt today for that reason alone.
# The one-character widening to `-?[[:space:]]*uses:` is NOT the fix: it hits
# `_selftest.yml`'s heredoc-written flawed fixture, which is not a real
# reference. Closing it properly means walking parsed YAML rather than grepping
# text. Behaviour here is deliberately unchanged from the inline version this
# replaced, and is pinned by a test case so it stays visible.
#
# Usage:
#   bash .github/workflows/scripts/audit-workflow-action-pins.sh [WORKFLOWS_DIR]
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dir="${1:-.github/workflows}"

# Command substitution, not process substitution: see the sibling audit's note.
WORKFLOW_LIST="$(bash "$script_dir/list-workflow-files.sh" "$dir")"
mapfile -t WORKFLOWS <<< "$WORKFLOW_LIST"

set +e
uses_lines="$(grep -nE '^[[:space:]]*uses:' "${WORKFLOWS[@]}")"
rc=$?
set -e

# 0 found, 1 none, anything else means the audit did not run to completion.
# The old inline form ended in `|| true`, which reported every one of the three
# as clean.
if [ "$rc" -gt 1 ]; then
  echo "::error::audit-workflow-action-pins: grep exited $rc --- the audit did not run to completion over ${#WORKFLOWS[@]} workflow file(s)." >&2
  exit 2
fi

# A workflow set with no `uses:` at all is legitimate, so an empty result here
# is a clean pass rather than a failure: discovery has already fail-closed on
# an empty file list, which is the case that would otherwise hide.
UNPINNED=""
if [ "$rc" -eq 0 ]; then
  # `uses:[[:space:]]*\.` already covers `uses: ./...`, so the two separate
  # local-ref filters the inline version carried are one filter here.
  UNPINNED="$(printf '%s\n' "$uses_lines" \
    | grep -v 'uses:[[:space:]]*\.' \
    | grep -v 'Morrison-Lab/gha' \
    | grep -vE '@[0-9a-f]{40}' || true)"
fi

if [ -n "$UNPINNED" ]; then
  printf '%s\n' "$UNPINNED"
  echo "::error::Unpinned third-party actions found in workflows (see gha#328); the offending lines are listed above."
  exit 1
fi

echo "All third-party actions in ${#WORKFLOWS[@]} workflow file(s) are SHA-pinned."
