#!/usr/bin/env bash
# Splits a comma-separated reviewers list into a JSON array of trimmed,
# non-empty GitHub usernames, ready to expand into `gh api -f
# reviewers[]=...` arguments. Extracted from request-dependabot-review.yml
# so the split/trim logic can be unit-tested offline instead of only
# exercised by a live Dependabot PR (gha#253 review: a bare `IFS=','
# read -ra` doesn't trim whitespace, so "alice, bob" sent an invalid
# `reviewers[]= bob` and failed the job).
#
# The splitting and trimming itself lives in split-csv-list.sh, which this
# script only reshapes into JSON -- the two used to carry separate copies of
# the same loop. That also replaces the `xargs` trim used here previously:
# `xargs` interprets quotes and backslashes as shell syntax, so a malformed
# username could fail the script rather than be passed through and rejected
# by the API.
#
# Usage: build-reviewer-args.sh <comma-separated-reviewers>
# Prints a JSON array (e.g. ["alice","bob"]) to stdout.
set -euo pipefail

REVIEWERS="${1:?usage: build-reviewer-args.sh <comma-separated-reviewers>}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# `-R -s` reads the whole stream as one string; the final newline yields a
# trailing empty element, which the length filter drops along with any other
# blanks. An all-blank list therefore gives `[]`, not `[""]`.
bash "$script_dir/split-csv-list.sh" "$REVIEWERS" \
  | jq -R -s -c 'split("\n") | map(select(length > 0))'
