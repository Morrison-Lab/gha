#!/usr/bin/env bash
# Exercises build-reviewer-args.sh's split/trim logic offline, mirroring
# run-sum-costs-tests.sh's pattern. Wired into _selftest.yml's
# `dependabot-review` job (gha#253 review finding).
#
# Usage: bash .github/workflows/scripts/tests/run-build-reviewer-args-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
build_script="$repo_root/.github/workflows/scripts/build-reviewer-args.sh"

# case: <reviewers input> -> expected JSON array
declare -A cases=(
  ["alice"]='["alice"]'
  ["alice,bob"]='["alice","bob"]'
  ["alice, bob"]='["alice","bob"]'
  [" alice , bob "]='["alice","bob"]'
  ["alice,,bob"]='["alice","bob"]'
)

failures=0
for input in "${!cases[@]}"; do
  want="${cases[$input]}"
  got="$(bash "$build_script" "$input")"
  if [[ "$got" == "$want" ]]; then
    echo "OK   build-reviewer-args.sh '$input' -> $got"
  else
    echo "::error::build-reviewer-args.sh '$input': expected $want but got $got"
    failures=$((failures + 1))
  fi
done

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of ${#cases[@]} build-reviewer-args case(s) did not behave as expected"
  exit 1
fi
echo "All ${#cases[@]} build-reviewer-args cases behaved as expected."
