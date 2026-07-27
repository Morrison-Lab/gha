#!/usr/bin/env bash
# Exercises select-existing-issue.sh's matching rule offline, mirroring
# run-build-reviewer-args-tests.sh's pattern. Wired into _selftest.yml's
# `failure-issue` job.
#
# Usage: bash .github/workflows/scripts/tests/run-select-existing-issue-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
select_script="$repo_root/.github/workflows/scripts/select-existing-issue.sh"

failures=0
total=0

# check <name> <title> <issues-json> <expected-stdout>
check() {
  local name="$1" title="$2" issues="$3" want="$4" got
  total=$((total + 1))
  got="$(printf '%s' "$issues" | bash "$select_script" "$title")"
  if [[ "$got" == "$want" ]]; then
    echo "OK   $name -> '${got:-<none>}'"
  else
    echo "::error::$name: expected '${want:-<none>}' but got '${got:-<none>}'"
    failures=$((failures + 1))
  fi
}

check "exact match" \
  "Publish failed on main" \
  '[{"number":7,"title":"Publish failed on main"}]' \
  "7"

check "no issues at all" \
  "Publish failed on main" \
  '[]' \
  ""

check "no matching title" \
  "Publish failed on main" \
  '[{"number":7,"title":"Something else entirely"}]' \
  ""

# The case the exact-match rule exists for: a longer title that merely starts
# with the one being matched must not be treated as the same failure.
check "prefix is not a match" \
  "Publish failed: website" \
  '[{"number":7,"title":"Publish failed: website preview"}]' \
  ""

check "case-sensitive" \
  "Publish failed on main" \
  '[{"number":7,"title":"publish failed on main"}]' \
  ""

# Duplicates already exist (e.g. filed before dedupe was in place): converge on
# the oldest rather than alternating between them.
check "duplicates converge on the lowest number" \
  "Publish failed on main" \
  '[{"number":12,"title":"Publish failed on main"},{"number":7,"title":"Publish failed on main"},{"number":30,"title":"Publish failed on main"}]' \
  "7"

check "picks the match, not the first entry" \
  "Publish failed on main" \
  '[{"number":3,"title":"Unrelated"},{"number":9,"title":"Publish failed on main"}]' \
  "9"

# Titles carry run-specific text in practice; make sure shell/jq metacharacters
# in a title are matched literally rather than interpreted.
check "title with quotes and special characters" \
  'Publish failed: "main" $RUN (100%)' \
  '[{"number":5,"title":"Publish failed: \"main\" $RUN (100%)"}]' \
  "5"

# An empty title is a caller bug: fail loudly rather than matching arbitrarily.
total=$((total + 1))
if printf '%s' '[{"number":7,"title":""}]' | bash "$select_script" "" 2>/dev/null; then
  echo "::error::empty title: expected a non-zero exit, but the script succeeded"
  failures=$((failures + 1))
else
  echo "OK   empty title -> non-zero exit"
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of $total select-existing-issue case(s) did not behave as expected"
  exit 1
fi
echo "All $total select-existing-issue cases behaved as expected."
