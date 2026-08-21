#!/usr/bin/env bash
# Compose the PR comment claude-code-review.yml posts when a review run
# finished but produced no usable verdict (gha#543).
#
# Why this exists at all. When "Resolve final review outcome" exits 1, every
# posting step downstream of it is gated on that step's outcome being
# `success` -- "Post quota-exhausted comment", "Post review comment", "Post
# cost comment", and "Collapse previous Claude review comments" all skip
# together. So a run that spent real money and reddened `require-review` left
# the PR thread completely silent, which from the thread is indistinguishable
# from a reviewer that simply has not started yet. This is the same
# silent-thread class gha#360 fixed for the push path and gha#379 for the
# Gemini path.
#
# Why it does NOT classify. Its two siblings, classify-push-failure.sh and
# classify-gemini-failure.sh, are handed raw error text and have to work out
# what happened. Nothing is left to work out here: check-review-execution.sh
# has already decided, and "Resolve final review outcome" has already picked
# which attempt's decision stands. Re-deriving that from the same evidence
# would be a second copy of the classification, free to drift out of step with
# the first -- the two-copies-of-one-pattern problem detect-review-request.sh
# records. So the kind is an INPUT, and this script's only judgment about it
# is to normalize an unrecognized value to `unknown` rather than render advice
# for a kind nobody defined.
#
# It keeps its siblings' four-part output contract even so -- `kind=`,
# `headline=`, a blank line, then the advice body -- because the calling
# composite reads those by fixed line offset, exactly as
# report-push-failure/report-gemini-failure do. `kind=` is echoed back rather
# than dropped so the caller reports the kind actually USED, which is what
# makes the normalization visible instead of silent.
#
# Contract:
#   line 1  kind=<normalized kind>
#   line 2  headline=<single line, reaches a Markdown alert title>
#   line 3  (blank)
#   line 4+ advice (Markdown, may span lines)
#
# Inputs come from the environment so a caller never has to quote a denied
# command string onto an argv:
#   FAILURE_KIND  `high-denial`, `stub`, `short-circuit`, `hard-error`,
#                 `no-output`, or `deferred`, as written by
#                 check-review-execution.sh; anything else normalizes to
#                 `unknown` and gets generic advice rather than a wrong story
#   DENIALS       permission_denials_count, or the 999999 sentinel, or empty
#   DENIED_TOOLS  check-review-execution.sh's denied_tools output (may be empty)
#   MAX_DENIALS   the stub-retry threshold the guard compared against; empty
#                 drops the threshold clause rather than guessing a default
#   TOTAL_COST    total_cost_usd summed across attempts (may be empty)
#   ATTEMPTS      how many review attempts ran ("1" or "2"; may be empty)
set -euo pipefail

FAILURE_KIND="${FAILURE_KIND:-}"
DENIALS="${DENIALS:-}"
DENIED_TOOLS="${DENIED_TOOLS:-}"
# No `:-5` fallback. Substituting the guard's own default here would put a
# second declaration of it in a second file, which is exactly what emitting
# max_denials from the guard was meant to avoid -- and it would print a
# threshold nobody compared against whenever STUB_RETRY_MAX_DENIALS was
# overridden and the value failed to arrive. Empty means "not known", and the
# threshold clause is dropped rather than guessed.
MAX_DENIALS="${MAX_DENIALS:-}"
TOTAL_COST="${TOTAL_COST:-}"
ATTEMPTS="${ATTEMPTS:-}"

case "$FAILURE_KIND" in
  high-denial|stub|short-circuit|hard-error|no-output|deferred) kind="$FAILURE_KIND" ;;
  *) kind=unknown ;;
esac

# The denial sentinel is 999999, which means the count could not be PARSED --
# not that there were a great many. check-review-execution.sh's own comments
# make the same point: collapsing unknown into "positive" is safe for the two
# gates that ask "may this be trusted?", and unsafe for any statement ABOUT
# the denials, which is exactly what this comment is. Printing "999999 denied
# tool calls" onto a PR would be a confident falsehood.
denials_phrase=""
if [[ "$DENIALS" == "999999" ]]; then
  denials_phrase="an unknown number of denied tool calls (the count could not be parsed from the execution output)"
elif [[ "$DENIALS" =~ ^[0-9]+$ ]]; then
  if [[ "$DENIALS" == "1" ]]; then
    denials_phrase="1 denied tool call"
  else
    denials_phrase="$DENIALS denied tool calls"
  fi
fi

case "$kind" in
  high-denial)
    headline="Claude review did not finish: no verdict, and the denial count was too high to retry."
    ;;
  stub)
    headline="Claude review did not finish: no verdict, on the first attempt and again on the retry."
    ;;
  short-circuit)
    headline="Claude review did not finish: the action exited without writing an execution result."
    ;;
  hard-error)
    headline="Claude review did not finish: the run ended in an error state."
    ;;
  no-output)
    headline="Claude review did not finish: the reviewer produced no output at all."
    ;;
  deferred)
    headline="Claude review did not run: the reviewer stood down over a session-lock claim comment."
    ;;
  *)
    headline="Claude review did not finish: no usable verdict was produced."
    ;;
esac

printf 'kind=%s\n' "$kind"
printf 'headline=%s\n' "$headline"
printf '\n'

# The first paragraph answers the question the silent thread could not: this
# is a failed reviewer, not a pending one.
# Deliberately says "finished without producing" rather than "ran to
# completion but never stated": this one paragraph is shared by every kind,
# and two of them did NOT run to completion -- a short-circuited action never
# got as far as reviewing, and a deferred reviewer stopped on purpose. A
# shared sentence has to be true of the whole set, or it contradicts the very
# headline printed two lines above it.
printf 'The review finished without producing a `### Verdict`, so **this PR has not been reviewed**. This comment exists so that fact is visible from the PR itself rather than only from the run log (gha#543).\n\n'

case "$kind" in
  high-denial)
    printf 'The reviewer was blocked often enough that it ran out of room before concluding'
    if [[ -n "$denials_phrase" ]]; then
      printf ': %s' "$denials_phrase"
      if [[ -n "$MAX_DENIALS" ]]; then
        printf ', above the stub-retry threshold of `%s`' "$MAX_DENIALS"
      fi
    fi
    printf '. This is gha#198'"'"'s signature rather than gha#185'"'"'s, so the workflow deliberately did **not** retry: that pattern has repeatedly failed to recover on a same-prompt retry, and each attempt costs real money.\n\n'
    printf 'Re-running this review unchanged is not the fix. Either widen the reviewer allowlist in `run-claude-review-attempt` so the denied calls are permitted, or adjust the review prompt so the reviewer stops attempting them.\n\n'
    ;;
  stub)
    printf 'The reviewer produced text but no verdict, on the first attempt and again on the automatic same-prompt retry'
    if [[ -n "$denials_phrase" ]]; then
      printf ' (%s)' "$denials_phrase"
    fi
    printf '. Two independent attempts agreeing makes a one-off unlikely.\n\n'
    printf 'Pushing a new commit re-triggers the review, and is worth one try. If it stubs a third time, treat the reviewer as unreachable for this PR and fall back to a self-review plus a cross-vendor reviewer.\n\n'
    ;;
  short-circuit)
    printf 'The action exited before writing an execution-output file, so there is no transcript to check for a verdict (gha#368). Nothing can be concluded about the diff from this run.\n\n'
    printf 'Check the `Run Claude Code Review` step in the linked run. A short-circuit there is usually a setup or credential failure rather than anything about the PR.\n\n'
    ;;
  hard-error)
    printf 'The run ended in an SDK-level error state'
    if [[ -n "$denials_phrase" ]]; then
      printf ' after %s' "$denials_phrase"
    fi
    printf '. The `Run Claude Code Review` step in the linked run carries the raw result object.\n\n'
    ;;
  no-output)
    printf 'The run completed without an SDK-level error but emitted no assistant text whatsoever, so there is nothing to check for a verdict. Whatever the reviewer did, none of it reached the transcript.\n\n'
    ;;
  deferred)
    printf 'The reviewer read a session-lock claim comment on this PR (`paws off until I am done`, `back off until done`, or similar) as an instruction to itself, and stopped without reviewing the diff (gha#527).\n\n'
    printf 'Those comments coordinate parallel **write** sessions. They are not addressed to automated review, and they never mean a review already ran. Re-trigger the review by pushing a commit; if it defers again, the claim comment is worth rewording.\n\n'
    ;;
  *)
    printf 'The specific failure mode was not identified. The `Resolve final review outcome` step in the linked run carries the annotation naming it.\n\n'
    ;;
esac

# The denied-tool names are the whole point of carrying this to the PR. A red
# check with only a count on it reads as "the reviewer gave up", where the
# names read as a permissions gap with a specific fix (gha#540).
#
# Empty and non-empty are different facts and get different lines. Empty means
# zero denials -- so saying nothing here would leave a reader to assume the
# names were merely unavailable, which is the opposite conclusion.
#
# Three cases, not two, for the same reason check-review-execution.sh tracks
# `denials_known` separately from the sentinel: "zero denials" and "no denial
# data" are different facts, and only one of them licenses the sentence that a
# reader will act on. A short-circuited run exits before the guard ever counts
# denials, so DENIALS arrives EMPTY there -- rendering that as "none" would
# assert the reviewer was not blocked by permissions, on a run where nothing is
# known about permissions at all, and would send a triager looking in the wrong
# place. The unknown-count sentinel does not reach this branch: the guard sets a
# non-empty DENIED_TOOLS wording for it.
if [[ -n "$DENIED_TOOLS" ]]; then
  printf '**Denied tools:** `%s`\n\n' "$DENIED_TOOLS"
elif [[ "$DENIALS" == "0" ]]; then
  printf '**Denied tools:** none. The reviewer was not blocked by tool permissions, so the cause lies elsewhere.\n\n'
else
  printf '**Denied tools:** not recorded. This run produced no usable denial data, so nothing can be concluded either way about tool permissions.\n\n'
fi

if [[ -n "$TOTAL_COST" ]]; then
  printf '**Cost:** $%s' "$TOTAL_COST"
  if [[ -n "$ATTEMPTS" ]]; then
    printf ' across %s attempt' "$ATTEMPTS"
    [[ "$ATTEMPTS" == "1" ]] || printf 's'
  fi
  printf ', spent on a run that produced no review.\n\n'
fi

printf 'Until an external verdict lands, this PR is **not** clean. The red `require-review` is correct rather than a flake, and a self-review stands in for the missing verdict without replacing it.\n'
