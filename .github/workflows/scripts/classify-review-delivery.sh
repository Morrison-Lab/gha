#!/usr/bin/env bash
# Decides whether a dispatched agent review actually DELIVERED a verdict, given
# the PR comments that name its run.
#
# Usage: printf '%s\0' <body> [<body> ...] | RUN_URL=... classify-review-delivery.sh
# Reads NUL-separated comment bodies on stdin and prints a two-line contract:
#
#   line 1  delivered=true|false
#   line 2  reason=<slug>
#
# ai-code-review.yml consults this after `gh run watch` returns, because a run
# CONCLUSION of `success` is not the same as "produced a verdict" (gha#362).
# claude-code-review.yml deliberately succeeds on a graceful quota skip
# (gha#520) and surfaces the skip through a comment instead, so the run-level
# conclusion cannot discriminate the commonest runtime failure there is. The
# discriminator has to be the agent's own PR-side outcome marker.
#
# Bodies arrive on stdin rather than as arguments for the reason
# detect-review-request.sh's header sets out at length: argv caps a single
# argument at MAX_ARG_STRLEN (131072 bytes) while a GitHub comment may be
# 65536 CHARACTERS, which in mostly-4-byte UTF-8 is twice that.
#
# WHY THIS TESTS FOR FAILURE RATHER THAN FOR A VERDICT.
# The obvious inversion -- require a positive verdict marker, treat its absence
# as "not delivered" -- needs each agent's SUCCESS marker, and getting one
# wrong makes every review by that agent fall through to a second agent. That
# costs a duplicate paid review and, on workflows sharing a per-PR
# `cancel-in-progress` group, can cancel the very review it was checking. The
# failure direction has no such blast radius: an unmatched marker leaves
# today's behaviour, which is the bug being narrowed rather than a new one.
#
# It is also complete for the two agents that emit markers, which is what makes
# the safe direction the correct one rather than merely the cautious one.
# gha#548 made claude-code-review.yml post a failure comment on EVERY
# no-verdict path (before it, those paths posted nothing at all), and
# gemini-code-review.yml has the equivalent through report-gemini-failure
# (gha#379). So for claude and gemini, "no failure marker" and "produced a
# verdict" coincide.
#
# Offline tests live in tests/run-classify-review-delivery-tests.sh.
set -euo pipefail

if [ -z "${RUN_URL:-}" ]; then
  echo "classify-review-delivery: RUN_URL is required." >&2
  exit 2
fi

# Every marker below is posted by a workflow in THIS repo, so these are fixed
# strings from a known producer rather than a heuristic over free text:
#
#   `Claude review did not finish:` / `did not run:`
#       every headline compose-review-failure-report.sh can emit (gha#548).
#   `Claude review skipped`  /  `Gemini review skipped`
#       the credential-or-quota notices, which predate those reporters and are
#       the case measured on gha#555: conclusion `success`, 44 seconds, no
#       verdict.
#   `Gemini CLI failed`
#       classify-gemini-failure.sh's `other` headline.
#
# A marker is matched only inside a comment that names THIS run, so a previous
# round's failure comment on the same PR cannot decide this round.
MARKERS=(
  'Claude review did not finish:|claude-failure'
  'Claude review did not run:|claude-stood-down'
  'Claude review skipped|claude-skipped'
  'Gemini review skipped|gemini-skipped'
  'Gemini CLI failed|gemini-failure'
)

saw_run_comment=false
matched_reason=""

while IFS= read -r -d '' body; do
  case "$body" in
    *"$RUN_URL"*) ;;
    *) continue ;;
  esac
  saw_run_comment=true

  for entry in "${MARKERS[@]}"; do
    needle="${entry%%|*}"
    slug="${entry##*|}"
    case "$body" in
      *"$needle"*)
        matched_reason="$slug"
        break
        ;;
    esac
  done

  [ -n "$matched_reason" ] && break
done

if [ -n "$matched_reason" ]; then
  printf 'delivered=false\n'
  printf 'reason=%s\n' "$matched_reason"
  exit 0
fi

# Two distinct ways to reach here, kept distinct in `reason` because they carry
# different amounts of information. A comment naming the run, with no failure
# marker in it, is positive evidence the agent got far enough to post. No
# comment naming the run at all says nothing either way -- an agent that emits
# no marker (cursor) looks identical to one that hung after `watch` returned --
# so the reason names that rather than implying a check was made.
if [ "$saw_run_comment" = true ]; then
  printf 'delivered=true\n'
  printf 'reason=no-failure-marker\n'
else
  printf 'delivered=true\n'
  printf 'reason=no-comment-names-this-run\n'
fi
