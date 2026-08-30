#!/usr/bin/env bash
# Offline table tests for compose-review-failure-report.sh (gha#543).
#
# What is worth testing here, and what is not. The script emits prose, and
# asserting prose word-for-word produces a suite that fails on every wording
# change while catching nothing. So the table asserts two things only:
#
#   1. The OUTPUT CONTRACT, by fixed line offset -- `kind=`, `headline=`, a
#      blank line, then the body. report-review-failure/action.yml reads those
#      three by `sed -n '1s/...'`, `sed -n '2s/...'`, and `tail -n +4`, so a
#      reordering breaks it silently, exactly as
#      run-classify-push-failure-tests.sh says of its own four-part contract.
#   2. The CLAIMS a reader would act on -- which failure kind was chosen, and
#      whether the denied-tool line says names / none / not recorded. Those are
#      the sentences that send a triager somewhere, and getting one wrong is
#      the whole failure mode this report exists to prevent.
#
# The denied-tools trio is the part to keep if this suite is ever trimmed. Its
# three cases are one fact each, and the middle one is the trap: DENIALS empty
# (a short-circuited run, where the guard exited before counting) must NOT
# render as "none", which would assert the reviewer was not blocked by
# permissions on a run where nothing about permissions is known.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="$SCRIPT_DIR/../compose-review-failure-report.sh"

failures=0
checks=0

check() {
  local label="$1" expected="$2" actual="$3"
  checks=$((checks + 1))
  if [[ "$expected" != "$actual" ]]; then
    printf 'FAIL: %s\n  expected: %s\n  actual:   %s\n' "$label" "$expected" "$actual"
    failures=$((failures + 1))
  fi
}

check_contains() {
  local label="$1" needle="$2" haystack="$3"
  checks=$((checks + 1))
  if [[ "$haystack" != *"$needle"* ]]; then
    printf 'FAIL: %s\n  missing: %s\n' "$label" "$needle"
    failures=$((failures + 1))
  fi
}

check_not_contains() {
  local label="$1" needle="$2" haystack="$3"
  checks=$((checks + 1))
  if [[ "$haystack" == *"$needle"* ]]; then
    printf 'FAIL: %s\n  unexpectedly present: %s\n' "$label" "$needle"
    failures=$((failures + 1))
  fi
}

run_compose() {
  FAILURE_KIND="${1:-}" DENIALS="${2:-}" DENIED_TOOLS="${3:-}" \
  MAX_DENIALS="${4:-}" TOTAL_COST="${5:-}" ATTEMPTS="${6:-}" \
    bash "$COMPOSE"
}

# --- kind normalization -----------------------------------------------------
# Every kind check-review-execution.sh can emit must survive unchanged; only a
# value it cannot emit normalizes. A kind silently rewritten to `unknown` would
# print generic advice under a specific headline, which is worse than either.
for kind in high-denial stub background-agent short-circuit hard-error no-output deferred bad-credential; do
  out="$(run_compose "$kind" 0)"
  check "kind passthrough: $kind" "kind=$kind" "$(sed -n 1p <<<"$out")"
done
for bogus in "" "nonsense" "HIGH-DENIAL"; do
  out="$(run_compose "$bogus" 0)"
  check "kind normalizes: '${bogus}'" "kind=unknown" "$(sed -n 1p <<<"$out")"
done

# --- output contract, by fixed line offset ---------------------------------
out="$(run_compose high-denial 12 'Taskx6 Bashx3' 5 1.77 1)"
check "line 1 is kind=" "kind=high-denial" "$(sed -n 1p <<<"$out")"
check_contains "line 2 is headline=" "headline=Claude review did not finish" "$(sed -n 2p <<<"$out")"
check "line 3 is blank" "" "$(sed -n 3p <<<"$out")"
check_contains "body starts at line 4" "has not been reviewed" "$(tail -n +4 <<<"$out")"

# The headline reaches a Markdown alert title (`> **...**`), which a newline
# would break out of. Assert there is exactly one headline= line and that
# nothing after it on that line wrapped.
check "exactly one headline line" "1" "$(grep -c '^headline=' <<<"$out")"

# --- the `stub` kind must not claim two attempts when only one ran ---------
# `stub` is reachable with ONE attempt behind it: attempt 1 classifies as a
# stub and the retry then fails its own gate and never runs. Claiming "two
# independent attempts agreeing" there contradicts the workflow's own
# annotation AND this report's own cost line on the same run -- the
# confidently-wrong-story failure the kind vocabulary exists to prevent
# (gha#548 review round 2).
out="$(run_compose stub 1 'Bashx1' 5 3.20 2)"
check_contains "two attempts: says so" 'and again on the automatic same-prompt retry' "$out"
check_contains "two attempts: draws the inference" 'Two independent attempts agreeing' "$out"

out="$(run_compose stub 1 'Bashx1' 5 0.90 1)"
check_not_contains "one attempt: does not claim a retry ran" 'and again on the automatic same-prompt retry' "$out"
check_not_contains "one attempt: does not claim two attempts agreed" 'Two independent attempts agreeing' "$out"
check_contains "one attempt: says the retry did not complete" 'did not run to completion' "$out"
# The headline is what a reader sees first, so it must agree with the body
# rather than only the body being fixed.
check_contains "one attempt: headline agrees with the body" 'headline=Claude review did not finish: no verdict, and the retry never ran to completion.' "$out"

# --- the denied-tools trio --------------------------------------------------
# 1. Names known: render them. This is the gha#540 payload, and carrying it to
#    the PR is the reason this report was worth building.
out="$(run_compose high-denial 12 'Taskx6 Bashx3' 5)"
check_contains "denied names are labelled" '**Denied tools:**' "$out"
check_contains "denied names are rendered" 'Taskx6 Bashx3' "$out"

# The value is FENCED rather than wrapped in a fixed one-backtick span,
# because it is agent-authored command text and a literal backtick in it is
# ordinary. A fixed delimiter closes early and mangles the rest of the posted
# comment (gha#548 review, finding 2).
#
# Both directions are pinned. A value with no backticks takes the minimum
# three-backtick fence; a value carrying a DOUBLE backtick run must widen past
# it, since a fence is closed by a run of equal length -- so a three-backtick
# fence would still be correct there and a naive one-backtick span would not,
# which is why the widening case uses a run long enough to discriminate.
out="$(run_compose high-denial 2 'Bashx2 plain' 5)"
check_contains "a backtick-free value takes the minimum fence" '```text' "$out"
backticky='Bashx2 (sample: Bash: echo `date` && x=```y```)'
out="$(run_compose high-denial 2 "$backticky" 5)"
check_contains "a value carrying a 3-run widens the fence" '````text' "$out"
check_contains "the backtick-carrying value survives intact" "$backticky" "$out"

# 2. A real zero: say none, positively.
out="$(run_compose hard-error 0 '')"
check_contains "zero denials says none" '**Denied tools:** none.' "$out"

# 3. Known denial count with names unavailable: report count and names unavailable (gha#764).
out="$(run_compose stub 4 '')"
check_contains "scalar denial count with empty names reports count and names unavailable" \
  '**Denied tools:** 4 denied tool calls, names unavailable.' "$out"
check_not_contains "scalar denial count does not report not recorded" \
  'not recorded' "$out"
out="$(run_compose stub 1 '')"
check_contains "single denial with empty names is singular" \
  '**Denied tools:** 1 denied tool call, names unavailable.' "$out"

# 4. No denial data at all (the short-circuit path, where the guard exits
#    before counting). Must NOT claim none -- that is a false statement about
#    permissions on a run that never measured them.
out="$(run_compose short-circuit '' '')"
check_contains "absent denial data is reported as unrecorded" '**Denied tools:** not recorded.' "$out"
check_not_contains "absent denial data does not claim none" '**Denied tools:** none.' "$out"

# --- the 999999 sentinel is not a number of denials -------------------------
# The guard hands over a non-empty DENIED_TOOLS wording for the unparseable
# case, so the sentinel must never be printed as a count.
out="$(run_compose high-denial 999999 'unknown -- the denial count itself could not be parsed' 5)"
check_not_contains "sentinel is never printed as a count" '999999 denied tool calls' "$out"

# --- the threshold is quoted only when it is known --------------------------
# Restating the guard's default here would print a threshold nobody compared
# against whenever STUB_RETRY_MAX_DENIALS was overridden and the value failed
# to arrive.
out="$(run_compose high-denial 12 'Taskx6' 9)"
check_contains "threshold quotes the value passed" 'threshold of `9`' "$out"
out="$(run_compose high-denial 12 'Taskx6' '')"
check_not_contains "no threshold clause when unknown" 'stub-retry threshold' "$out"
check_contains "denial count still reported without a threshold" '12 denied tool calls' "$out"

# --- cost -------------------------------------------------------------------
out="$(run_compose stub 1 'Bashx1' 5 3.20 2)"
check_contains "cost is reported" 'across 2 attempts' "$out"
out="$(run_compose stub 1 'Bashx1' 5 1.00 1)"
check_contains "single attempt is not pluralized" 'across 1 attempt,' "$out"
out="$(run_compose stub 1 'Bashx1' 5 '' '')"
check_not_contains "no cost line when cost is unknown" '**Cost:**' "$out"

# --- singular/plural on the denial count ------------------------------------
# Asserted as "not plural" rather than as a fixed following character: what
# follows the count depends on whether a threshold clause comes next, so
# anchoring on the punctuation would test the threshold branch by accident.
out="$(run_compose high-denial 1 'Bashx1' 5)"
check_contains "one denial is singular" '1 denied tool call' "$out"
check_not_contains "one denial is not pluralized" '1 denied tool calls' "$out"
out="$(run_compose high-denial 2 'Bashx2' 5)"
check_contains "two denials are plural" '2 denied tool calls' "$out"

# --- shell metacharacters in a denied command are inert and preserved -------
# DENIED_TOOLS is assembled from the COMMANDS the reviewer attempted, so it is
# agent-authored free text and routinely contains quotes, `$`, `;`, and
# redirects -- gha#541's whole subject was a reviewer reaching for
# `gh pr diff ... > /tmp/pr.diff`. The first draft of the calling workflow
# interpolated it straight into a `run:` body with `${{ }}`, where a sample
# carrying `$(...)` executed inside a job holding CLAUDE_CODE_OAUTH_TOKEN;
# that is fixed by passing it through `env:` instead, which YAML cannot express
# a test for here. What this case pins is the half that IS testable: the script
# must render such a value verbatim, neither executing nor mangling it, so a
# future rewrite reaching for `eval` or an unquoted expansion is caught.
#
# ONE assertion, deliberately. A `check_not_contains` was tried here and
# removed: any needle naming the substituted result had to be either the bare
# username (which can legitimately appear elsewhere in a report) or a marker
# string that no version of the script could ever emit -- and the marker form
# passes under every mutation including the one it was written for, which is
# the vacuous-negative shape CLAUDE.md already records for `must_not_log`.
# The positive check is what actually pins this: under an `eval` regression the
# literal `$(id -un)` is replaced by its output, so the verbatim match fails.
# Confirmed by mutation rather than assumed (gha#548 review, finding 3).
hostile='Bashx1 (sample: Bash: gh pr diff 1 > /tmp/d; echo $(id -un) & rm -rf "x")'
out="$(run_compose high-denial 1 "$hostile" 5)"
check_contains "shell metacharacters survive verbatim" "$hostile" "$out"

# --- the report must stay ASCII ---------------------------------------------
# check-non-standard-chars scans .qmd/.R/.md and so does not reach this script,
# but the body it emits is posted as Markdown and its siblings
# (classify-push-failure.sh, classify-gemini-failure.sh) are ASCII-only. Pin it
# rather than leaving it to a checker that does not run here.
out="$(run_compose high-denial 12 'Taskx6' 5 1.77 1)"
checks=$((checks + 1))
if LC_ALL=C grep -q '[^[:print:][:space:]]' <<<"$out"; then
  printf 'FAIL: report body contains non-ASCII characters\n'
  failures=$((failures + 1))
fi

# --- the background-agent kind must say the non-retry was deliberate --------
# The reader's next move is what the advice decides: a triager who reads this
# as an ordinary stub re-triggers and pays for another doomed attempt, so the
# claims asserted are the deliberate non-retry and where the durable fix
# lives (the omitted-parameter gap the gha#550 deny rule cannot reach).
out="$(run_compose background-agent 0 '' 5 4.19 1)"
check_contains "background-agent names the mechanism" 'background' "$out"
check_contains "background-agent says the non-retry was deliberate" 'deliberately did **not** retry' "$out"
check_contains "background-agent names the omitted-parameter gap" 'what the deny rule cannot match' "$out"
# Its three claims are each false of the other kinds and each actionable, so
# they are asserted rather than left to the headline. A reader acts on "this is
# a repo secret, not the diff", so that is the one to keep if trimmed.
out="$(FAILURE_KIND=bad-credential DENIALS='' DENIED_TOOLS='' MAX_DENIALS='' \
  TOTAL_COST=0.0000 ATTEMPTS=1 bash "$COMPOSE")"
check_contains "bad-credential names the secret" 'CLAUDE_CODE_OAUTH_TOKEN' "$out"
check_contains "bad-credential exonerates the diff" 'rather than anything about the diff' "$out"
# A run that never started has no denial data and no spend. Reporting either
# would send a triager to look at permissions or at cost on a run that reached
# neither -- the same wrong-place-to-look problem the denied-tools trio exists
# to prevent, which is why these are NEGATIVE assertions rather than reworded
# positive ones. Both were confirmed to fail before the suppression landed.
check_not_contains "bad-credential reports no denial line" '**Denied tools:**' "$out"
check_not_contains "bad-credential reports no cost line" '**Cost:**' "$out"
# The shared opening paragraph claims the review "finished without producing" a
# verdict, which is false of a run the pre-flight stopped before it started.
check_not_contains "bad-credential does not claim the review finished" \
  'The review finished without producing' "$out"

# --- every kind produces a non-empty, distinct headline ---------------------
# A kind whose headline duplicated another's would misdescribe the failure
# while looking fine in isolation.
seen=""
for kind in high-denial stub background-agent short-circuit hard-error no-output deferred bad-credential unknown; do
  headline="$(run_compose "$kind" 0 | sed -n '2s/^headline=//p')"
  checks=$((checks + 1))
  if [[ -z "$headline" ]]; then
    printf 'FAIL: %s has an empty headline\n' "$kind"
    failures=$((failures + 1))
  elif [[ "$seen" == *"|$headline|"* ]]; then
    printf 'FAIL: %s reuses another kind'"'"'s headline: %s\n' "$kind" "$headline"
    failures=$((failures + 1))
  fi
  seen="$seen|$headline|"
done

printf '\n%d checks, %d failures\n' "$checks" "$failures"
[[ "$failures" -eq 0 ]]
