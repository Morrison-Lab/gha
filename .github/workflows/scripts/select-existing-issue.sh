#!/usr/bin/env bash
# Picks the open issue an automated failure report should be appended to,
# given the candidate issues and the title the report would use.
#
# Extracted from the open-failure-issue composite so the matching rule can be
# unit-tested offline, rather than only being exercised by a live failing
# workflow run -- the same reasoning behind build-reviewer-args.sh (gha#253).
#
# The rule is an exact, case-sensitive title match. A substring or fuzzy match
# would fold together two genuinely different failures whose titles share a
# prefix (e.g. "Publish failed: website" and "Publish failed: website preview"),
# which is worse than opening one issue too many: the second failure's evidence
# would land on an issue about the first and be read as the same problem.
#
# Usage: select-existing-issue.sh <title> < issues.json
#   issues.json is `gh issue list --state open --json number,title` output:
#   a JSON array of {"number": N, "title": "..."} objects.
#
# Prints the number of the lowest-numbered exact match, or nothing when there
# is no match. Lowest-numbered rather than newest so a run picks the original
# report when duplicates already exist, letting them converge on one issue
# instead of alternating.
set -euo pipefail

# `:?` rather than `?`: an empty title is a caller bug, not a request to match
# every untitled issue, so fail fast instead of matching something arbitrary.
TITLE="${1:?usage: select-existing-issue.sh <title> < issues.json}"

jq -r --arg title "$TITLE" '
  map(select(.title == $title) | .number)
  | min
  | select(. != null)
'
