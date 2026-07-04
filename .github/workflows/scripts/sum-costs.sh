#!/usr/bin/env bash
# Sums two total_cost_usd values, each of which may be empty (meaning that
# attempt didn't run, or reported no cost), formatted to 4 decimal places.
# Extracted from claude-code-review.yml's "Resolve final review outcome"
# step -- which sums the initial attempt's cost with the gha#185 stub-retry
# attempt's cost, when a retry ran -- so the arithmetic can be unit-tested
# offline instead of only exercised by a live two-attempt review run
# (gha#219 review finding 5).
#
# Usage: sum-costs.sh <cost-a> <cost-b>
# Prints the formatted sum to stdout. Either argument may be an empty string.
set -euo pipefail

A="${1:-}"
B="${2:-}"

awk -v a="${A:-0}" -v b="${B:-0}" 'BEGIN { printf "%.4f", a + b }'
