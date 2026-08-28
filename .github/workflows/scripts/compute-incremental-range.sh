#!/usr/bin/env bash
# Compute the what-changed-since-the-last-reviewed-commit section (gha#709).
#
# A reviewer deriving the incremental range from comment history has
# misstated it -- naming one commit where the range held two -- and then
# approved on the strength of the misstated range (d-morrison/altdoc#125).
# So the workflow computes the range with git itself and hands it to the
# reviewer as authoritative.
#
# Usage: compute-incremental-range.sh <comments-json-file>
#
# The argument is a file holding ONE JSON array of the PR's issue comments
# (all pages merged; the caller runs `gh api --paginate | jq -s 'add // []'`).
# The prior reviewed commit is the last `Reviewed commit: <sha>` line in the
# most recent verdict-bearing bot comment -- the same population
# claude-code-review.yml's gather-context fetch step matches on.
#
# Runs inside the PR checkout. That checkout is fetch-depth: 1, so the prior
# SHA is normally NOT reachable at first: the script deepens the fetch in
# DEEPEN_STEP-commit increments (default 50) until the prior commit is an
# ancestor of HEAD, giving up -- and emitting nothing -- once DEEPEN_MAX
# (default 500) is reached or the repository is no longer shallow (a
# force-pushed-away or otherwise orphaned prior SHA). Without the deepening
# this feature is inert on every real round, which is exactly what gha#717's
# review round 1 measured.
#
# Stdout: the markdown section, or nothing when the range is not computable
# (first round, unparseable comments, unreachable prior, prior == head).
# Every not-computable path exits 0: this is an optional enrichment, and it
# must never redden the review job it feeds (the same rule the guard's
# denied-tools summary follows).
#
# Output uses INDENTED blocks rather than fences, so a commit subject
# carrying backticks cannot close the block early.
set -euo pipefail

COMMENTS_FILE="${1:?usage: compute-incremental-range.sh <comments-json-file>}"
DEEPEN_STEP="${DEEPEN_STEP:-50}"
DEEPEN_MAX="${DEEPEN_MAX:-500}"

if [ ! -f "$COMMENTS_FILE" ]; then
  exit 0
fi

PRIOR=$(jq -r '
  [ .[]?
    | select((.user.login == "github-actions[bot]" or .user.login == "claude[bot]")
             and (.body | test("### (Code Review|Verdict)"))) ]
  | last | .body // ""
' "$COMMENTS_FILE" 2>/dev/null \
  | grep -oE 'Reviewed commit: [0-9a-f]{40}' | tail -1 | awk '{print $3}' || true)

HEAD_NOW=$(git rev-parse HEAD 2>/dev/null || true)

if [ -z "$PRIOR" ] || [ -z "$HEAD_NOW" ] || [ "$PRIOR" = "$HEAD_NOW" ]; then
  exit 0
fi

# Deepen a shallow checkout until the prior commit is an ancestor of HEAD.
# Order matters inside the loop: once the repository is no longer shallow,
# an un-reached prior is orphaned (force-push) and no fetch will change
# that -- give up rather than loop.
deepened=0
until git merge-base --is-ancestor "$PRIOR" "$HEAD_NOW" 2>/dev/null; do
  if [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" != "true" ]; then
    exit 0
  fi
  if [ "$deepened" -ge "$DEEPEN_MAX" ]; then
    exit 0
  fi
  # Deepen against the checked-out SHA explicitly: a bare
  # `git fetch --deepen` covers only the default refs/heads/* refspec, and
  # the ordinary pull_request checkout is refs/pull/<n>/merge -- not on any
  # branch -- so the bare form never reaches the prior there (gha#717
  # review round 2, confirmed against both checkout topologies).
  git fetch -q --deepen="$DEEPEN_STEP" origin "$HEAD_NOW" 2>/dev/null || exit 0
  deepened=$((deepened + DEEPEN_STEP))
done

LOG=$(git log --oneline "$PRIOR..$HEAD_NOW" 2>/dev/null | sed 's/^/    /' || true)
if [ -z "$LOG" ]; then
  exit 0
fi
STAT=$(git diff --stat "$PRIOR" "$HEAD_NOW" 2>/dev/null | sed 's/^/    /' || true)

printf '%s\n' \
  '## What changed since the last review round (computed)' \
  '' \
  "The prior round reviewed commit \`$PRIOR\`; this checkout's head is \`$HEAD_NOW\`. The range below was computed by the workflow with git itself. When you describe what changed since the last round, describe THIS range rather than deriving your own, and examine every commit and file in it:" \
  '' \
  "    \$ git log --oneline ${PRIOR:0:8}..${HEAD_NOW:0:8}" \
  "$LOG" \
  '' \
  "    \$ git diff --stat ${PRIOR:0:8} ${HEAD_NOW:0:8}" \
  "$STAT"
