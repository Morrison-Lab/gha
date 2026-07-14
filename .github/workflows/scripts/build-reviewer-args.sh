#!/usr/bin/env bash
# Splits a comma-separated reviewers list into a JSON array of trimmed,
# non-empty GitHub usernames, ready to expand into `gh api -f
# reviewers[]=...` arguments. Extracted from request-dependabot-review.yml
# so the split/trim logic can be unit-tested offline instead of only
# exercised by a live Dependabot PR (gha#253 review: a bare `IFS=','
# read -ra` doesn't trim whitespace, so "alice, bob" sent an invalid
# `reviewers[]= bob` and failed the job).
#
# Usage: build-reviewer-args.sh <comma-separated-reviewers>
# Prints a JSON array (e.g. ["alice","bob"]) to stdout.
set -euo pipefail

REVIEWERS="${1:?usage: build-reviewer-args.sh <comma-separated-reviewers>}"

json='[]'
IFS=',' read -ra reviewer_list <<< "$REVIEWERS"
for reviewer in "${reviewer_list[@]}"; do
  trimmed="$(echo "$reviewer" | xargs)"
  [[ -z "$trimmed" ]] && continue
  json="$(jq -c --arg r "$trimmed" '. + [$r]' <<< "$json")"
done

echo "$json"
