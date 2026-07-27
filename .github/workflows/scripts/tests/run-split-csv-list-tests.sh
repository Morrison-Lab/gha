#!/usr/bin/env bash
# Exercises split-csv-list.sh offline, mirroring run-build-reviewer-args-tests.sh's
# pattern. Wired into _selftest.yml's `failure-issue` job.
#
# Usage: bash .github/workflows/scripts/tests/run-split-csv-list-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
split_script="$repo_root/.github/workflows/scripts/split-csv-list.sh"

failures=0
total=0

# check <name> <input> <expected newline-separated output>
check() {
  local name="$1" input="$2" want="$3" got
  total=$((total + 1))
  got="$(bash "$split_script" "$input")"
  if [[ "$got" == "$want" ]]; then
    echo "OK   $name"
  else
    echo "::error::$name: expected $(printf '%q' "$want") but got $(printf '%q' "$got")"
    failures=$((failures + 1))
  fi
}

check "single item"            "bug"                 $'bug'
check "no spaces"              "bug,automated"       $'bug\nautomated'
# The case that motivated the script: gh's own flag parser does not trim, so
# an untrimmed " automated" matches no label and fails the whole create call.
check "space after comma"      "bug, automated"      $'bug\nautomated'
check "padded on both sides"   " bug , automated "   $'bug\nautomated'
check "empty entries dropped"  "bug,,automated"      $'bug\nautomated'
check "trailing comma"         "bug,"                $'bug'
check "empty string"           ""                    ""
check "only commas and spaces" " , , "               ""
# Labels legitimately contain spaces, so trimming must not collapse them.
check "internal spaces kept"   "good first issue, bug" $'good first issue\nbug'
check "tabs treated as space"  $'\tbug\t,automated'  $'bug\nautomated'

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of $total split-csv-list case(s) did not behave as expected"
  exit 1
fi
echo "All $total split-csv-list cases behaved as expected."
