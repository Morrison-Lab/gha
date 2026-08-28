#!/usr/bin/env bash
# Fail when any workflow passes SUBMODULES_TOKEN to a top-level checkout's
# `token:` input (gha#442).
#
# That secret authenticates a cross-owner SUBMODULE fetch, so it must never
# gate the caller's own repo checkout --- a consumer that sets it correctly for
# its own submodule is exactly the consumer whose main checkout then fails,
# since the token has no reason to be able to read the caller's repo. Use the
# checkout-submodules composite's `submodules-token:` input instead.
#
# The anchor is a line-leading `token:`, not a bare substring, so this does not
# also flag `submodules-token:` (which legitimately carries the secret): a
# trimmed line starting "submodules-token:" never matches a pattern requiring
# "token:" immediately after the leading whitespace.
#
# Lives in a script rather than inline in `_selftest.yml` so the grep's exit
# status can be read three ways rather than two, and so the whole audit is
# testable offline against fixtures that carry the violation (gha#716).
#
# Usage:
#   bash .github/workflows/scripts/audit-workflow-token-usage.sh [WORKFLOWS_DIR]
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dir="${1:-.github/workflows}"

# Command substitution, not process substitution: a discovery failure inside
# `< <(...)` never reaches mapfile, so the array would come back empty, `set -e`
# would not fire, and grep with no file arguments would read stdin and pass
# having examined nothing.
WORKFLOW_LIST="$(bash "$script_dir/list-workflow-files.sh" "$dir")"
mapfile -t WORKFLOWS <<< "$WORKFLOW_LIST"

# POSIX character classes rather than GNU's `\s`, so the pattern means the same
# thing under BSD grep on a maintainer's machine as under GNU grep on a runner.
PATTERN='^[[:space:]]*token:[[:space:]]*\$\{\{[^}]*SUBMODULES_TOKEN'

set +e
hits="$(grep -nE "$PATTERN" "${WORKFLOWS[@]}")"
rc=$?
set -e

# grep answers three ways, not two: 0 found, 1 clean, anything else means the
# check itself failed to run (an unreadable or vanished file). Collapsing that
# third case into "clean" is how an audit passes over a file it never read.
if [ "$rc" -gt 1 ]; then
  echo "::error::audit-workflow-token-usage: grep exited $rc --- the audit did not run to completion over ${#WORKFLOWS[@]} workflow file(s)." >&2
  exit 2
fi

if [ "$rc" -eq 0 ]; then
  printf '%s\n' "$hits"
  echo "::error::A workflow above passes SUBMODULES_TOKEN to a top-level actions/checkout 'token:' input (see gha#442) --- it authenticates a cross-owner submodule fetch, not the caller's own repo. Use the checkout-submodules composite's 'submodules-token:' input instead."
  exit 1
fi

echo "No workflow passes SUBMODULES_TOKEN to a top-level checkout token: input (${#WORKFLOWS[@]} file(s) examined)."
