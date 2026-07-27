#!/usr/bin/env bash
# Splits a comma-separated list into one trimmed, non-empty item per line.
#
# Exists because a bare `IFS=',' read -ra` does not trim, and the consumers of
# these lists reject the untrimmed result in ways that are hard to read back
# from the error. `gh issue create --label` is the case that motivated it:
# its flag is a Cobra StringSlice, which splits on commas through Go's
# csv.Reader with TrimLeadingSpace off, so `"bug, automated"` becomes
# `bug` and ` automated` -- and the leading space makes the second match no
# label in the repository, failing the whole call. gha#253 hit the same shape
# in build-reviewer-args.sh, where `"alice, bob"` sent `reviewers[]= bob`.
#
# Items may contain spaces (`good first issue` is a real GitHub label), so
# only leading and trailing whitespace is removed -- not internal.
#
# Usage: split-csv-list.sh <comma-separated-list>
# Prints one item per line; prints nothing for an empty or all-blank list.
set -euo pipefail

LIST="${1-}"

IFS=',' read -ra raw_items <<< "$LIST"
for item in "${raw_items[@]}"; do
  # Strip leading then trailing whitespace. `xargs` would collapse internal
  # runs and choke on quotes, so do it with parameter expansion instead.
  trimmed="${item#"${item%%[![:space:]]*}"}"
  trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
  [[ -z "$trimmed" ]] && continue
  printf '%s\n' "$trimmed"
done
