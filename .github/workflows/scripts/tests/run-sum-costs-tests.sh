#!/usr/bin/env bash
# Exercises sum-costs.sh's arithmetic offline, mirroring run-fixture-tests.sh's
# pattern. Wired into _selftest.yml's `review-fail-check` job (gha#219 review
# finding 5).
#
# Usage: bash .github/workflows/scripts/tests/run-sum-costs-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
sum_script="$repo_root/.github/workflows/scripts/sum-costs.sh"

# case: "<cost-a>|<cost-b>" -> expected formatted sum
declare -A cases=(
  ["0.30|0.12"]="0.4200"
  ["|0.05"]="0.0500"
  ["0.08|"]="0.0800"
  ["|"]="0.0000"
  ["2.2062398500000007|"]="2.2062"
)

failures=0
for case in "${!cases[@]}"; do
  a="${case%%|*}"
  b="${case##*|}"
  want="${cases[$case]}"
  got="$(bash "$sum_script" "$a" "$b")"
  if [[ "$got" == "$want" ]]; then
    echo "OK   sum-costs.sh '$a' '$b' -> $got"
  else
    echo "::error::sum-costs.sh '$a' '$b': expected $want but got $got"
    failures=$((failures + 1))
  fi
done

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of ${#cases[@]} sum-costs case(s) did not behave as expected"
  exit 1
fi
echo "All ${#cases[@]} sum-costs cases behaved as expected."
