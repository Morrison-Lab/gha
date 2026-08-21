#!/usr/bin/env bash
# Offline table tests for classify-review-delivery.sh (gha#362).
#
# The interesting cases are the ones a verdict-level test cannot tell apart:
# a failure marker on the WRONG run, and a comment that names this run without
# carrying any marker. Both return delivered=true, for different reasons, and
# conflating them would hide a real regression.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../classify-review-delivery.sh"
RUN_URL="https://github.com/Morrison-Lab/gha/actions/runs/32525696286"
OTHER_RUN="https://github.com/Morrison-Lab/gha/actions/runs/99999999999"

failures=0
checked=0

check() {
  local name="$1" want_delivered="$2" want_reason="$3"
  shift 3
  local out got_delivered got_reason
  out="$(printf '%s\0' "$@" | RUN_URL="$RUN_URL" bash "$SCRIPT")"
  got_delivered="$(sed -n '1s/^delivered=//p' <<<"$out")"
  got_reason="$(sed -n '2s/^reason=//p' <<<"$out")"
  checked=$((checked + 1))
  if [ "$got_delivered" != "$want_delivered" ] || [ "$got_reason" != "$want_reason" ]; then
    echo "FAIL: $name"
    echo "  want: delivered=$want_delivered reason=$want_reason"
    echo "  got:  delivered=$got_delivered reason=$got_reason"
    failures=$((failures + 1))
  fi
}

# --- the measured case this exists for (gha#555): conclusion success, no verdict
check "quota skip notice naming this run" false claude-skipped \
  "> **Claude review skipped — API credential or quota unavailable.** No secret is configured. [View run]($RUN_URL)"

# --- every compose-review-failure-report.sh headline family
check "claude did-not-finish headline" false claude-failure \
  "> [!CAUTION]
> **Claude review did not finish: no verdict, and the denial count was too high to retry.**

[View run]($RUN_URL)"

check "claude stood-down headline" false claude-stood-down \
  "**Claude review did not run: the reviewer stood down over a session-lock claim comment.** [run]($RUN_URL)"

# --- gemini's two reporters
check "gemini quota skip" false gemini-skipped \
  "> **Gemini review skipped — API key or quota unavailable.** [View run]($RUN_URL)"

check "gemini other-failure headline" false gemini-failure \
  "> [!CAUTION]
> **Gemini CLI failed for a reason other than quota/auth/suspension.** [run]($RUN_URL)"

# --- delivered: a real verdict comment naming this run
check "verdict comment naming this run" true no-failure-marker \
  "**Claude finished review** — [View run]($RUN_URL)

### Verdict

**Ready for merge.**"

# --- the discriminating negative: a failure marker on a DIFFERENT run must not
#     decide this one. Without this case, scoping by run URL could be dropped
#     and every test above would still pass.
check "failure marker on another run is ignored" true no-comment-names-this-run \
  "> **Claude review skipped — API credential or quota unavailable.** [View run]($OTHER_RUN)"

# --- a previous round's failure beside this round's success: the marker is
#     present on the PR but not on this run, so this run counts as delivered.
check "previous round failure plus this round verdict" true no-failure-marker \
  "> **Claude review skipped — API credential or quota unavailable.** [View run]($OTHER_RUN)" \
  "**Claude finished review** — [View run]($RUN_URL)

### Verdict

**Ready for merge.**"

# --- an agent that emits no marker at all (cursor) is indistinguishable from a
#     run that posted nothing, and must keep today's accept-on-success behaviour
check "no comments at all" true no-comment-names-this-run ""

check "only unrelated comments" true no-comment-names-this-run \
  "Working on this --- paws off until I'm done." \
  "💰 **Cost:** \$1.34 — [run]($OTHER_RUN)"

# --- the cost comment names this run and is not a failure marker
check "cost comment naming this run is not a marker" true no-failure-marker \
  "💰 **Cost:** \$1.34 ([review](https://github.com/x/y/pull/1)) — [run]($RUN_URL)"

# --- a failure marker anywhere in a long body, not just at the start
check "marker mid-body" false claude-failure \
  "Some preamble.

More text that goes on for a while.

> **Claude review did not finish: the run ended in an error state.**

[View run]($RUN_URL)"

# --- RUN_URL is required
if printf '%s\0' "x" | bash "$SCRIPT" >/dev/null 2>&1; then
  echo "FAIL: missing RUN_URL should exit non-zero"
  failures=$((failures + 1))
fi
checked=$((checked + 1))

echo "classify-review-delivery: examined $checked cases, $failures failed."
[ "$failures" -eq 0 ]
