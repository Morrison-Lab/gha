#!/usr/bin/env bash
# Offline tests for list-workflow-files.sh (gha#716).
#
# The negative cases are the ones to keep if this suite is ever trimmed. A
# discovery helper that silently returns nothing, or that sweeps in files
# GitHub never loads, fails in the direction that makes every audit built on
# it report clean --- so an empty directory must be an error, and a nested or
# non-workflow file must not appear.
#
# Usage: bash .github/workflows/scripts/tests/run-list-workflow-files-tests.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIST="$script_dir/../list-workflow-files.sh"

if [ ! -f "$LIST" ]; then
  echo "::error::list-workflow-files.sh not found at $LIST" >&2
  exit 1
fi

failures=0
cases=0

expect_output() {
  local label="$1" dir="$2" want="$3"
  cases=$((cases + 1))
  local got
  got="$(bash "$LIST" "$dir" 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ' | sed 's/ $//')"
  if [ "$got" != "$want" ]; then
    echo "::error::$label: expected '$want', got '$got'" >&2
    failures=$((failures + 1))
  else
    echo "OK   $label"
  fi
}

expect_failure() {
  local label="$1" dir="$2" needle="$3"
  cases=$((cases + 1))
  local out rc
  out="$(bash "$LIST" "$dir" 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "::error::$label: expected a non-zero exit, got 0 with output '$out'" >&2
    failures=$((failures + 1))
  elif ! printf '%s' "$out" | grep -qF "$needle"; then
    echo "::error::$label: expected output to mention '$needle', got '$out'" >&2
    failures=$((failures + 1))
  else
    echo "OK   $label"
  fi
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# 1. Both extensions are discovered, sorted, and nothing else is.
both="$tmp/both"
mkdir -p "$both/scripts"
: > "$both/a.yml"
: > "$both/b.yaml"
: > "$both/c.txt"
: > "$both/scripts/nested.yml"
expect_output "both extensions discovered, .txt and nested ignored" "$both" "a.yml b.yaml"

# 2. A .yaml-only directory is not mistaken for an empty one.
yamlonly="$tmp/yaml-only"
mkdir -p "$yamlonly"
: > "$yamlonly/only.yaml"
expect_output "a .yaml-only directory is discovered" "$yamlonly" "only.yaml"

# 3. An empty directory fails closed rather than printing nothing.
empty="$tmp/empty"
mkdir -p "$empty"
expect_failure "an empty workflows directory is an error" "$empty" "no .yml or .yaml workflow files"

# 4. A missing directory fails closed too.
expect_failure "a missing workflows directory is an error" "$tmp/absent" "workflows directory not found"

if [ "$failures" -ne 0 ]; then
  echo "::error::$failures of $cases list-workflow-files test case(s) failed" >&2
  exit 1
fi
echo "All $cases list-workflow-files tests passed."
