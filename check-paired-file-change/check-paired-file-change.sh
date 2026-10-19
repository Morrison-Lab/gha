#!/usr/bin/env bash
#
# Fail a pull request that changes a file matching `trigger-paths` without
# also changing a file matching `required-paths`, unless the PR carries the
# skip label. The motivating pair is a macro library and the page that
# documents its notation (Morrison-Lab/macros#248), but nothing here knows
# that: the two sets of paths are the caller's.
#
# Three design choices are load-bearing.
#
# The matching is done by GIT. Both path sets are git pathspecs, passed to
# `git diff --name-only`, so no glob dialect is reimplemented here. A
# pathspec needs `:(glob)` magic for `**`; a bare `*` also crosses `/`.
#
# The diff is the PR's own: `base-ref...HEAD`. On a pull_request event the
# checkout is GitHub's merge ref and `HEAD^1` is the base tip it was built on
# (the payload's base.sha can lag that tip; gha#1007). A renamed file counts
# as both paths (the pathspec filters before rename detection), so moving a
# trigger file is a trigger change and moving a required file satisfies the
# pairing.
#
# The skip label is read LIVE from the API, never from the event payload,
# which is frozen at the triggering event and stale for any label applied
# later (gha#721). The read happens only on the failing path, is paginated,
# and is fail-loud: a swallowed API error would read as "no labels" and
# reproduce the stale-exemption defect. An empty skip-label never matches.
set -euo pipefail

trim_split() {
  # Split on commas and newlines, strip surrounding whitespace, drop blanks.
  printf '%s\n' "$1" \
    | tr ',' '\n' \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
    | grep -v '^$' || :
}

base_ref="${PFC_BASE_REF:-}"
if [ -z "$base_ref" ]; then
  echo "::notice::check-paired-file-change: no base-ref (not a pull request run), so there is no diff to check. Skipping."
  exit 0
fi

mapfile -t trigger_specs < <(trim_split "${PFC_TRIGGER_PATHS:-}")
mapfile -t required_specs < <(trim_split "${PFC_REQUIRED_PATHS:-}")

# A check with no paths is a green check that examined nothing.
if [ "${#trigger_specs[@]}" -eq 0 ]; then
  echo "::error::check-paired-file-change: trigger-paths is empty after parsing, so nothing would be checked."
  exit 1
fi
if [ "${#required_specs[@]}" -eq 0 ]; then
  echo "::error::check-paired-file-change: required-paths is empty after parsing, so the pairing could never be satisfied."
  exit 1
fi

changed_matching() {
  git diff --name-only "$base_ref...HEAD" -- "$@"
}

if ! triggered="$(changed_matching "${trigger_specs[@]}")"; then
  echo "::error::check-paired-file-change: could not diff '$base_ref...HEAD'. Check out with fetch-depth: 0."
  exit 1
fi

if [ -z "$triggered" ]; then
  echo "No changed file matches trigger-paths; nothing to pair."
  exit 0
fi

required="$(changed_matching "${required_specs[@]}")"
if [ -n "$required" ]; then
  echo "Changed files matching trigger-paths are paired with a change to:"
  printf '  %s\n' "$required"
  exit 0
fi

# Failing path: look for the skip label, read live.
skip_label="$(printf '%s' "${PFC_SKIP_LABEL:-}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
if [ -n "$skip_label" ] && [ -n "${PFC_PR_NUMBER:-}" ]; then
  labels="$("${PFC_GH:-gh}" api --paginate \
    "repos/${GITHUB_REPOSITORY}/issues/${PFC_PR_NUMBER}/labels" --jq '.[].name')"
  skip_lc="$(printf '%s' "$skip_label" | tr '[:upper:]' '[:lower:]')"
  while IFS= read -r label; do
    [ -z "$label" ] && continue
    label_lc="$(printf '%s' "$label" | tr '[:upper:]' '[:lower:]')"
    if [ "$label_lc" = "$skip_lc" ]; then
      echo "::notice::check-paired-file-change: the PR carries the '$skip_label' label, so the pairing is not required."
      exit 0
    fi
  done <<< "$labels"
fi

message="${PFC_MESSAGE:-}"
[ -n "$message" ] || message="Update a file matching required-paths in the same pull request."
echo "::error title=Paired file change missing::${message//$'\n'/ }"
echo "Changed files matching trigger-paths:"
printf '  %s\n' "$triggered"
echo "No changed file matches required-paths: $(trim_split "${PFC_REQUIRED_PATHS:-}" | paste -sd, - | sed 's/,/, /g')"
if [ -n "$skip_label" ]; then
  echo "To skip this check, add the '$skip_label' label to the pull request and re-run."
fi
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "### Paired file change missing"
    echo
    echo "$message"
    echo
    echo "Changed files matching \`trigger-paths\`:"
    echo
    # shellcheck disable=SC2016  # literal backticks for Markdown
    while IFS= read -r f; do printf -- '- `%s`\n' "$f"; done <<< "$triggered"
  } >> "$GITHUB_STEP_SUMMARY"
fi
exit 1
