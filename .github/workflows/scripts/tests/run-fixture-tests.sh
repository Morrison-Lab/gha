#!/usr/bin/env bash
# Exercises check-review-execution.sh's fail-check guard logic against canned
# execution-output fixtures, offline (no live Claude API call). Wired into
# _selftest.yml's `review-fail-check` job (#174).
#
# Usage: bash .github/workflows/scripts/tests/run-fixture-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
check_script="$repo_root/.github/workflows/scripts/check-review-execution.sh"
fixtures_dir="$script_dir/fixtures"

# fixture file -> expected outcome:
#   pass      — check-review-execution.sh exits 0 and writes review_text_file
#   fail      — it exits non-zero, and does NOT write stub_review=true
#   fail-stub — it exits non-zero AND writes stub_review=true (gha#185's
#               retryable signature: real, non-empty text, no verdict, and a
#               LOW permission_denials_count — distinct from a hard SDK
#               error, genuinely empty output, or gha#198's textually
#               identical but high-denial-count pattern, none of which
#               claude-code-review.yml retries)
#   skip      — it exits 0 and writes quota_exhausted=true (graceful skip)
declare -A expected=(
  [genuine-finished-review.json]=pass
  [stub-pr171-waiting-background-agents.json]=fail-stub
  [stub-pr171-remaining-review-agents.json]=fail-stub
  [stub-sparta590-scheduled-wakeup.json]=fail-stub
  [stub-sparta590-unnecessary-call.json]=fail-stub
  [stub-gha198-high-denial-count.json]=fail
  # gha#550: a fan-out stopped by the deliberate background-spawn deny
  # rules. The raw denial count (8) is over the threshold; the
  # starvation-relevant count is 0, so the retry must survive.
  [spawn-denials-only-retryable.json]=fail-stub
  # The same 8 intended denials beside 6 genuinely-starved calls, which
  # is what keeps the exclusion from blinding the gha#198 gate.
  [spawn-denials-plus-starved-calls.json]=fail
  # gha#551: a no-verdict run whose transcript carries EXECUTED background
  # Agent spawns (explicit run_in_background:true, no matching denial) must
  # NOT be retried -- `fail`, not `fail-stub`, is the assertion that
  # stub_review stays unwritten. Built from the real run-32347489886
  # artifact's shape (ai-config#1744).
  [stub-background-agents-executed.json]=fail
  # The same, with run_in_background OMITTED entirely: the parameter
  # defaults to true and an omitted parameter is exactly what the gha#550
  # deny rule cannot match, so the detector must test != false, not == true.
  [stub-background-agents-omitted-param.json]=fail
  # The discriminating negative: a SYNCHRONOUS fan-out (every spawn carries
  # run_in_background:false) that stubbed for an unrelated reason is the
  # gha#185 shape that genuinely recovers on retry sometimes -- it must stay
  # a retryable stub, or the new kind is a behaviour regression (the
  # over-matching caution in gha#551's own body).
  [stub-sync-agents-only.json]=fail-stub
  # The subtraction's own discriminator: both background spawns appear in
  # the transcript AND in permission_denials (what a real denied call looks
  # like post-gha#550), so none executed and the retry must survive. The
  # spawn-denials-only fixtures cannot catch a dropped subtraction, because
  # they carry no transcript tool_use blocks at all -- confirmed by mutation
  # (executed_bg_spawns=$bg_spawn_uses left every other fixture green).
  [stub-denied-bg-spawns-in-transcript.json]=fail-stub
  [empty-review-text.json]=fail
  [is-error-result.json]=fail
  # gha#391: is_error:true alongside subtype:"success" is a self-contradictory
  # result. When a genuine verdict was already posted, the review already did
  # its job and the check must not hide it (was `fail` before this fix).
  # is-error-success-with-verdict.json mirrors #984's/#985's logged
  # is_error/subtype pair (Group A -- verdict posted, check failed anyway,
  # both merged unread); is-error-success-no-verdict.json mirrors #986's
  # logged run numbers (Group B -- no verdict, real content). When no verdict
  # was posted, the anomaly gets no special treatment: still `fail`, and
  # deliberately NOT `fail-stub` -- retrying a result shape nobody has
  # evidence recovers is a separate decision this fix does not make (see
  # check-review-execution.sh's own comment at that check).
  [is-error-success-with-verdict.json]=pass
  [is-error-success-no-verdict.json]=fail
  # gha#561: turn-1 zero-cost execution failure with subtype:"success" is an
  # execution/runtime error, NOT quota exhaustion. Must fail as hard-error.
  [is-error-success-turn1-zerocost.json]=fail
  # gha#446 review finding 1: permission_denials_count can be JSON null
  # (observed real evidence, not hypothetical -- see the null-denials comment
  # in check-review-execution.sh). A denied `gh pr comment`/`gh api ...
  # comments` attempt must not be trusted as a posted verdict just because
  # the denial count is unknown rather than a confirmed 0; both directions
  # (is_error:true+subtype:success, and the pre-existing is_error:false path)
  # must still `fail` rather than being fooled into `pass`/`fail-stub`.
  [is-error-success-denied-comment-null-denials.json]=fail
  [denied-comment-null-denials-not-trusted.json]=fail
  [quota-exhausted.json]=skip
  [quota-exhausted-with-message.json]=skip
  # gha#520: the same exhaustion reached part-way through a review instead of at
  # the door -- real turns, real cost, api_error_status:429. The zero-cost /
  # turn-1 branch cannot see it, so before the fix this fell through to the hard
  # is_error exit and reddened the check over an account condition. The
  # with-verdict variant pins the ordering against gha#391: a run that stated
  # its verdict and only then hit the limit already did its job, so it must
  # still `pass` rather than being swallowed as a skip.
  [quota-exhausted-midrun.json]=skip
  [quota-exhausted-midrun-with-verdict.json]=pass
  [verdict-label-format.json]=pass
  # gha#710: a review split across assistant blocks, each carrying a verdict
  # line -- the posted text must be the whole span, not the tail. The
  # must_contain needle is block A's analysis, which the pre-#710 last-block
  # extraction dropped.
  [verdict-split-across-blocks.json]=pass
  # gha#805: three complete drafts, each with a `### Verdict` heading. Only
  # the last is posted; the gha#710 span rule alone concatenates all three.
  [verdict-redrafted-thrice.json]=pass
  # gha#808 review: a later block that only QUOTES a verdict heading (in a
  # fence, and in a blockquote) is not a draft; the real review before it
  # must be posted, not dropped.
  [verdict-then-quoted-heading.json]=pass
  [verdict-not-last-block.json]=pass
  [verdict-via-inline-comment-tool.json]=pass
  [verdict-via-gh-comment-heredoc.json]=pass
  [verdict-via-gh-comment-heredoc-tag-in-body.json]=pass
  [verdict-via-gh-comment-heredoc-dash-tab.json]=pass
  [verdict-via-gh-comment-heredoc-crlf.json]=pass
  [denied-bash-comment-not-trusted.json]=fail-stub
  [claim-comment-deferred-review.json]=fail
  [claim-comment-deferred-verdict-only.json]=fail
  [short-circuit-no-result.json]=fail-short-circuit
  # gha#531: a real execution file can carry `permission_denials` (an array
  # of denial-detail objects) with NO `permission_denials_count` scalar at
  # all -- the count must fall back to the array's length rather than
  # defaulting to the MISSING sentinel, which would wrongly force `fail`
  # (no retry) even when the true count is within the stub-retry threshold.
  [permission-denials-array-only-low-count.json]=fail-stub
  [permission-denials-array-only-high-count.json]=fail
  # gha#540 & gha#756: a mixed-tool denial array where unparameterized Task
  # denials (6) are subtracted as intended denials, leaving 5 starvation
  # denials (<= max_denials 5). Pins that unparameterized Task denials are
  # excluded from the retry gate, yielding a retryable stub rather than high-denial.
  [permission-denials-mixed-tools.json]=fail-stub
  # gha#540: a denial array carrying entries the summarizer cannot index -- a
  # string `tool_input`, and a bare string where an object belongs. The
  # OUTCOME is the point here: without `?`-suppressed lookups the jq filter
  # raises "Cannot index string with string", `set -e` aborts the script at
  # exit 5, and the review is never classified at all -- so this fixture
  # asserts the ordinary `fail-stub` verdict is still reached (3 denials, at
  # or under the threshold), not merely that some log line appeared.
  [permission-denials-malformed-entries.json]=fail-stub
)

# For `pass` fixtures where the posted review_text_file's content matters
# (gha#173): the block it must contain, and a block it must NOT contain.
declare -A must_contain=(
  [verdict-not-last-block.json]='Ready for merge'
  # The needle is the MIDDLE, non-verdict block: it discriminates both the
  # pre-#710 tail-only extraction (which drops it along with block A) and a
  # hypothetical first+last-only join (which keeps A but drops it).
  [verdict-split-across-blocks.json]='middle-pass rerun of the suite'
  # Two needles in one: the third draft, and the tail AFTER it (a line-start
  # Verdict: line, no heading), which must be kept -- narrowing the span end
  # to the last heading block drops the tail.
  [verdict-redrafted-thrice.json]='gamma-pass fixture table'
  [verdict-then-quoted-heading.json]='epsilon-pass analysis'
  # gha#391: confirms review_text_file carries the actual posted verdict, not
  # just an empty/fallback string from the is_error early-fail path.
  [is-error-success-with-verdict.json]='Ready for merge'
  # gha#218 review finding 2: review_text_file must carry the actual
  # verdict-bearing content (from the inline-comment tool's body), not
  # just fall back to the narration text block that happens to satisfy
  # the pass/fail scan.
  [verdict-via-inline-comment-tool.json]='Ready for merge'
  # The review lives inside a `gh pr comment ... <<EOF ... EOF` heredoc body.
  # review_text_file must carry that unwrapped body, not the raw command
  # string (which would post a literal `gh pr comment ...` block to the PR).
  [verdict-via-gh-comment-heredoc.json]='One real finding on line 12'
  # gha#318 review finding 1: the review body itself contains lines that start
  # with the heredoc tag (`EOF markers must...`, and an indented `    EOF`
  # inside a quoted shell example) before the real terminator. Only a
  # whole-line terminator match reaches the verdict below them; a
  # word-boundary or leading-whitespace-tolerant one stops at the first of
  # those and posts a review truncated to its first heading.
  [verdict-via-gh-comment-heredoc-tag-in-body.json]='Ready for merge'
  # The <<- form strips leading TABS from the body, so the posted text must
  # come out de-indented -- tab-indented markdown renders as a code block.
  [verdict-via-gh-comment-heredoc-dash-tab.json]='### Verdict'
  # A CRLF transcript: the terminator is still found, and the posted body
  # comes out with the carriage returns stripped rather than carrying them
  # into the PR comment (gha#318 review round 2).
  [verdict-via-gh-comment-heredoc-crlf.json]='**Ready for merge**'
  # gha#520: the verdict survives the 429 -- review_text_file must carry the
  # posted verdict rather than an empty fallback from the error path.
  [quota-exhausted-midrun-with-verdict.json]='Ready for merge'
)
# gha#808 review: a second must-contain needle where one fixture pins two
# claims. Checked exactly like must_contain.
declare -A must_also_contain=(
  [verdict-redrafted-thrice.json]='delta-pass tail is retained'
)

declare -A must_not_contain=(
  # gha#805: the superseded first draft must not be posted. Its needle is
  # what the pre-#805 span rule (first verdict block through last) keeps.
  [verdict-redrafted-thrice.json]='alpha-pass fixture table'
  [verdict-not-last-block.json]="I've posted my findings"
  [verdict-via-inline-comment-tool.json]="Posted the inline finding and a summary comment ending in"
  [verdict-via-gh-comment-heredoc.json]='gh pr comment'
  [verdict-via-gh-comment-heredoc-tag-in-body.json]='gh pr comment'
  [verdict-via-gh-comment-heredoc-dash-tab.json]=$'\t### Verdict'
  [verdict-via-gh-comment-heredoc-crlf.json]=$'\r'
)

# gha#540: what the script LOGS, as distinct from what it posts or how it
# exits. The count on its own sent two readers to a wrong cause for the same
# failure, so the denied tool NAMES are behaviour worth pinning rather than
# incidental output -- and every direction below fails silently if it
# regresses (a missing name reads as a quiet log, not as a broken check).
#
# Each entry is a substring the script's combined stdout/stderr must contain.
declare -A must_log=(
  # Grouping, count-descending ordering, and one argument sample PER TOOL --
  # the six Task denials must appear in their own sample rather than being
  # crowded out by alphabetically-earlier arguments from other tools.
  [permission-denials-mixed-tools.json]='Denied tools: Taskx6 Bashx3 WebFetchx2 (sample: Task: review one file; Bash: gh api repos/Morrison-Lab/gha/pulls/1; WebFetch: https://example.invalid/spec)'
  # The array-length fallback path (no scalar count) still names the tools.
  [permission-denials-array-only-high-count.json]='Denied tools: Bashx8 (sample: Bash: gh api repos/x/y)'
  # NOT gated on the over-threshold branch: a low-count run is retried and can
  # stub again, so it needs the same diagnostic.
  [permission-denials-array-only-low-count.json]='Denied tools: Bashx5 (sample: Bash: gh pr diff 1744)'
  # The mirror of the gha#531 case: a scalar count with NO array. Saying so
  # explicitly matters -- an empty list would read as "nothing was denied",
  # which is the fail-open direction.
  # Anchored on the whole log line, not the bare phrase "names unavailable":
  # the over-threshold annotation carries that phrase too, as its own
  # ${denied_summary:-...} fallback, so a shorter needle passes even when this
  # log line is deleted -- confirmed by mutation, which is how the first draft
  # of this assertion was caught passing vacuously.
  # A malformed entry degrades to `unknown` / the tool name rather than
  # taking the summary (or the script) down with it.
  [permission-denials-malformed-entries.json]='Denied tools: Bashx1 WebFetchx1 unknownx1'
  [stub-gha198-high-denial-count.json]='Denied tools: names unavailable -- the execution result carries no permission_denials array'
  # An UNPARSEABLE count is a different fact from a known-positive count with
  # no array, and must not borrow its wording: the first says nothing about
  # whether any denial occurred (gha#544 review).
  [denied-comment-null-denials-not-trusted.json]='Denied tools: unknown -- the denial count itself could not be parsed'
  # gha#551: the executed-spawn arithmetic is logged where it is computed, so
  # a triager can see the subtraction (uses minus denied) rather than only
  # the verdict. Anchored on the whole line: the counts are what a broken
  # subtraction would silently change.
  [stub-background-agents-executed.json]='executed_background_spawns=2 (tool_use with run_in_background != false: 2; denied: 0)'
)
declare -A must_not_log=(
  # The redaction case is NOT here -- it is generated at runtime below, since a
  # committed credential-shaped literal would trip the `secrets` job's own
  # history scan forever after.
  # A clean run must not gain a "Denied tools:" line at all -- the summary is
  # a diagnostic for denials, not noise on every review.
  #
  # TWO fixtures, and the second is the one that matters: `denials` is
  # three-valued (a real 0, a real positive count, or the 999999 UNKNOWN
  # sentinel), so a guard written as `denials != 0` treats unknown as
  # positive. genuine-finished-review.json cannot catch that -- its count is
  # a literal 0, so the branch never fires for it either way, and the first
  # draft of this map passed while a CLEAN PASS was being told it had
  # denials. is-error-success-with-verdict.json carries
  # `permission_denials_count: null`, which is the case that discriminates.
  [genuine-finished-review.json]='Denied tools'
  [is-error-success-with-verdict.json]='Denied tools'
  # Same sentinel, reaching the over-threshold annotation instead of the log
  # line: it must say "unknown", never the no-array wording.
  [denied-comment-null-denials-not-trusted.json]='names unavailable'
)

assert_log() {
  local fixture="$1" log_file="$2"
  if [[ -n "${must_log[$fixture]:-}" ]] && ! grep -qF "${must_log[$fixture]}" "$log_file"; then
    echo "::error::fixture $fixture: log is missing expected text: ${must_log[$fixture]}"
    return 1
  fi
  if [[ -n "${must_not_log[$fixture]:-}" ]] && grep -qF "${must_not_log[$fixture]}" "$log_file"; then
    echo "::error::fixture $fixture: log contains text it must not: ${must_not_log[$fixture]}"
    return 1
  fi
  return 0
}

# total_cost_usd is written unconditionally whenever a result object is
# parsed (gha#219) — every fixture below has one, so every fixture asserts
# an exact cost regardless of its pass/fail/fail-stub/skip outcome. Values
# are each fixture's result.total_cost_usd, verbatim as `jq -r` prints it.
declare -A expected_cost=(
  [genuine-finished-review.json]=0.42
  [spawn-denials-only-retryable.json]=4.21
  [verdict-split-across-blocks.json]=1.11
  [verdict-redrafted-thrice.json]=2.34
  [verdict-then-quoted-heading.json]=1.42
  [spawn-denials-plus-starved-calls.json]=3.9
  [stub-background-agents-executed.json]=4.19
  [stub-background-agents-omitted-param.json]=4.18
  [stub-sync-agents-only.json]=4.17
  [stub-denied-bg-spawns-in-transcript.json]=4.16
  [stub-pr171-waiting-background-agents.json]=0.05
  [stub-pr171-remaining-review-agents.json]=0.08
  [stub-sparta590-scheduled-wakeup.json]=0.03
  [stub-sparta590-unnecessary-call.json]=0.03
  [stub-gha198-high-denial-count.json]=2.2062398500000007
  [empty-review-text.json]=0.01
  [is-error-result.json]=0.15
  [is-error-success-with-verdict.json]=6.23
  [is-error-success-no-verdict.json]=0.97
  [is-error-success-turn1-zerocost.json]=0
  [is-error-success-denied-comment-null-denials.json]=1.1
  [denied-comment-null-denials-not-trusted.json]=1.1
  [quota-exhausted.json]=0
  [quota-exhausted-with-message.json]=0
  [quota-exhausted-midrun.json]=4.100043149999999
  [quota-exhausted-midrun-with-verdict.json]=4.31
  [verdict-label-format.json]=0.31
  [verdict-not-last-block.json]=0.37
  [verdict-via-inline-comment-tool.json]=0.55
  [verdict-via-gh-comment-heredoc.json]=0.61
  [verdict-via-gh-comment-heredoc-tag-in-body.json]=0.72
  [verdict-via-gh-comment-heredoc-dash-tab.json]=0.83
  [verdict-via-gh-comment-heredoc-crlf.json]=0.94
  [denied-bash-comment-not-trusted.json]=0.4
  [claim-comment-deferred-review.json]=0.67
  [claim-comment-deferred-verdict-only.json]=0.42
  [short-circuit-no-result.json]=""
  [permission-denials-array-only-low-count.json]=4.21
  [permission-denials-array-only-high-count.json]=3.5
  [permission-denials-mixed-tools.json]=2.75
  [permission-denials-malformed-entries.json]=1.25
)

# gha#543: which failure each non-zero exit reports. claude-code-review.yml's
# review-failure comment is written from this, so a wrong kind produces a
# confidently wrong explanation on the PR -- a worse outcome than the silence
# it replaced, and one nothing else in this suite can see (the exit code and
# stub_review are identical across `hard-error`, `no-output`, and
# `high-denial`).
#
# Asserted for EVERY fixture, not only the failing ones: a `pass` or `skip`
# fixture must write no failure_kind at all, since a stale kind left on a
# clean run is what would let the comment describe a failure that did not
# happen.
declare -A expected_kind=(
  [stub-pr171-waiting-background-agents.json]=stub
  [stub-pr171-remaining-review-agents.json]=stub
  [stub-sparta590-scheduled-wakeup.json]=stub
  [stub-sparta590-unnecessary-call.json]=stub
  [denied-bash-comment-not-trusted.json]=stub
  [permission-denials-array-only-low-count.json]=stub
  [permission-denials-malformed-entries.json]=stub
  [stub-gha198-high-denial-count.json]=high-denial
  [spawn-denials-only-retryable.json]=stub
  [spawn-denials-plus-starved-calls.json]=high-denial
  [stub-background-agents-executed.json]=background-agent
  [stub-background-agents-omitted-param.json]=background-agent
  # All spawns synchronous: the new kind must NOT claim it (gha#551).
  [stub-sync-agents-only.json]=stub
  # All spawns denied: none executed, so the retry survives (gha#551).
  [stub-denied-bg-spawns-in-transcript.json]=stub
  [permission-denials-array-only-high-count.json]=high-denial
  [permission-denials-mixed-tools.json]=stub
  # A denied `gh pr comment` leaves the count non-zero but unparseable/known
  # -- these reach the no-verdict branch, and which side of the threshold
  # they land on is what decides the kind. Both carry the 999999 sentinel,
  # which is above it.
  [is-error-success-denied-comment-null-denials.json]=hard-error
  [denied-comment-null-denials-not-trusted.json]=high-denial
  [is-error-result.json]=hard-error
  [is-error-success-no-verdict.json]=hard-error
  [is-error-success-turn1-zerocost.json]=hard-error
  [empty-review-text.json]=no-output
  [short-circuit-no-result.json]=short-circuit
  [claim-comment-deferred-review.json]=deferred
  [claim-comment-deferred-verdict-only.json]=deferred
)

# gha#543: `max_denials` is emitted so the review-failure comment can quote
# the threshold this run actually compared against, instead of restating the
# script's default in a second file (the two-declarations-of-one-default
# problem gha#303 pinned a test against).
#
# Asserted as an INVARIANT rather than per fixture: it is written immediately
# after `denials`, unconditionally, so the two must always co-occur. Keying on
# that relationship rather than on a per-fixture table means a fixture added
# later cannot forget to declare it -- and it pins the value, so a caller
# reading an empty output and silently falling back to a hard-coded 5 would
# still be caught here rather than on a live review.
assert_max_denials() {
  local output_file="$1"
  local denials max_denials
  denials="$(sed -n 's/^denials=//p' "$output_file" | tail -1)"
  max_denials="$(sed -n 's/^max_denials=//p' "$output_file" | tail -1)"
  if [[ -z "$denials" ]]; then
    # Exited before the denial count was computed (no result object, or an
    # early quota skip). Neither output should be present.
    [[ -z "$max_denials" ]]
  else
    [[ "$max_denials" == "5" ]]
  fi
}

# gha#548 review, finding 8: `denied_tools` is written immediately after
# `denials`, so the two must co-occur -- present together, or absent together.
#
# This pins a CONTRACT that was previously only asserted in prose, and asserted
# wrongly: run-review-guard's own docs claimed the output was "set on every
# exit path", which is false for the two short-circuit exits that return before
# the denial count exists. Prose cannot be run; this can. The distinction
# matters to a caller, because an ABSENT value means "never counted" while an
# EMPTY-but-present one means "counted, and there were none" -- and only the
# second licenses saying the reviewer was not blocked by permissions.
#
# Note `grep -q '^denied_tools='` rather than a non-empty check: the value is
# legitimately empty on a zero-denial run, so presence and content are
# different questions and only presence is the invariant here.
assert_denied_tools_presence() {
  local output_file="$1"
  local denials
  denials="$(sed -n 's/^denials=//p' "$output_file" | tail -1)"
  if [[ -z "$denials" ]]; then
    ! grep -q '^denied_tools=' "$output_file"
  else
    grep -q '^denied_tools=' "$output_file"
  fi
}

assert_kind() {
  local fixture="$1" output_file="$2"
  local want="${expected_kind[$fixture]:-}" got
  # tail -1: the script appends, and a fixture that trips two branches would
  # otherwise compare against the first. Only the last write is the verdict.
  got="$(sed -n 's/^failure_kind=//p' "$output_file" | tail -1)"
  [[ "$got" == "$want" ]]
}

assert_cost() {
  local fixture="$1" output_file="$2"
  local want="${expected_cost[$fixture]:-}" got
  got="$(sed -n 's/^total_cost_usd=//p' "$output_file")"
  [[ "$got" == "$want" ]]
}

assert_pass() {
  local fixture="$1" exit_code="$2" output_file="$3"
  [[ "$exit_code" -eq 0 ]] && grep -q '^review_text_file=' "$output_file" || return 1

  local posted_file
  posted_file="$(sed -n 's/^review_text_file=//p' "$output_file")"
  if [[ -n "${must_contain[$fixture]:-}" ]] && ! grep -qF "${must_contain[$fixture]}" "$posted_file"; then
    return 1
  fi
  if [[ -n "${must_also_contain[$fixture]:-}" ]] && ! grep -qF "${must_also_contain[$fixture]}" "$posted_file"; then
    return 1
  fi
  if [[ -n "${must_not_contain[$fixture]:-}" ]] && grep -qF "${must_not_contain[$fixture]}" "$posted_file"; then
    return 1
  fi
  # gha#805, as an invariant over every posted review rather than one
  # fixture: a comment carries at most ONE authored verdict heading. A second
  # means two complete drafts were concatenated, whichever fixture produced
  # them. The gha#710 tail writes `Verdict:` without a heading, so it does
  # not count; nor does a heading inside a fenced block or a blockquote,
  # excluded here the same way the extractor excludes them (gha#808 review:
  # the first draft of this counted them, so a correct single-draft review
  # that quoted one example heading would have failed). No interval
  # expression in the awk, per this repo's mawk rule. This is a shape check
  # on our own extraction, not a verdict parse.
  local headings
  headings="$(awk '
    /^[ \t]?[ \t]?[ \t]?(```|~~~)/ { fence = !fence; next }
    fence { next }
    /^[ \t]*>/ { next }
    tolower($0) ~ /^[ \t]*#+[ \t]*verdict/ { n++ }
    END { print n + 0 }' "$posted_file")"
  if [[ "$headings" -gt 1 ]]; then
    echo "::error::$fixture: posted review carries $headings verdict headings (gha#805)"
    return 1
  fi
  return 0
}

assert_fail() {
  local exit_code="$1" output_file="$2"
  [[ "$exit_code" -ne 0 ]] && ! grep -q '^stub_review=true$' "$output_file"
}

assert_fail_stub() {
  local exit_code="$1" output_file="$2"
  [[ "$exit_code" -ne 0 ]] && grep -q '^stub_review=true$' "$output_file"
}

assert_fail_short_circuit() {
  local exit_code="$1" output_file="$2"
  [[ "$exit_code" -ne 0 ]] && grep -q '^action_short_circuit=true$' "$output_file"
}

# gha#804: a graceful skip names WHICH quota case fired, so the PR notice
# can say a configured credential was refused (or accepted, then 429'd)
# rather than guessing that no secret exists. Asserted per fixture, since
# the two skip shapes are exactly what the reason has to tell apart; the
# mid-run case must also carry the API's own message, single-line.
declare -A expected_quota_reason=(
  [quota-exhausted.json]=rejected-at-door
  [quota-exhausted-with-message.json]=rejected-at-door
  [quota-exhausted-midrun.json]=midrun-429
)
declare -A expected_quota_message=(
  [quota-exhausted.json]=""
  # Multi-line in the fixture; the guard collapses it, and this is the only
  # fixture whose door-path message is non-empty, so a broken door-path
  # extraction (wrong key, dropped gsub) has nowhere else to show.
  [quota-exhausted-with-message.json]="Invalid Authorization header value from CLAUDE_CODE_OAUTH_TOKEN: it contains a line break at character 56 (see the run log)"
  [quota-exhausted-midrun.json]="You've hit your weekly limit · resets Aug 20, 8pm (UTC)"
)

assert_skip() {
  local fixture="$1" exit_code="$2" output_file="$3"
  [[ "$exit_code" -eq 0 ]] && grep -q '^quota_exhausted=true$' "$output_file" || return 1
  local got_reason got_message
  got_reason="$(sed -n 's/^quota_reason=//p' "$output_file" | tail -1)"
  got_message="$(sed -n 's/^quota_message=//p' "$output_file" | tail -1)"
  [[ "$got_reason" == "${expected_quota_reason[$fixture]:-}" ]] || return 1
  [[ "$got_message" == "${expected_quota_message[$fixture]:-}" ]]
}

# The converse: a run that did not skip must not carry a reason. A stale
# reason on a passing run would make the posting job describe a skip that
# did not happen, and the with-verdict 429 fixture is the one that can leak
# one (hoisting the 429 block above the verdict check does it). Only this
# direction is asserted: the positive half is already pinned per fixture by
# assert_skip, so restating it here could never fail on its own.
assert_no_stale_quota_reason() {
  local output_file="$1"
  if grep -q '^quota_exhausted=true$' "$output_file"; then
    return 0
  fi
  ! grep -q '^quota_reason=' "$output_file"
}

failures=0
for fixture in "${!expected[@]}"; do
  want="${expected[$fixture]}"
  output_file="$(mktemp)"
  log_file="$(mktemp)"

  set +e
  GITHUB_OUTPUT="$output_file" bash "$check_script" "$fixtures_dir/$fixture" >"$log_file" 2>&1
  exit_code=$?
  set -e

  ok=false
  case "$want" in
    pass) assert_pass "$fixture" "$exit_code" "$output_file" && ok=true ;;
    fail) assert_fail "$exit_code" "$output_file" && ok=true ;;
    fail-stub) assert_fail_stub "$exit_code" "$output_file" && ok=true ;;
    fail-short-circuit) assert_fail_short_circuit "$exit_code" "$output_file" && ok=true ;;
    skip) assert_skip "$fixture" "$exit_code" "$output_file" && ok=true ;;
    *) echo "::error::unknown expected outcome '$want' for fixture $fixture"; exit 1 ;;
  esac

  if [[ "$ok" == "true" ]] && ! assert_no_stale_quota_reason "$output_file"; then
    echo "::error::$fixture: quota_reason leaked onto a run that did not skip (gha#804)"
    ok=false
  fi
  if [[ "$ok" == "true" ]] && ! assert_cost "$fixture" "$output_file"; then
    ok=false
    echo "::error::fixture $fixture: total_cost_usd mismatch (want ${expected_cost[$fixture]}, got $(sed -n 's/^total_cost_usd=//p' "$output_file"))"
  fi

  if [[ "$ok" == "true" ]] && ! assert_max_denials "$output_file"; then
    ok=false
    echo "::error::fixture $fixture: max_denials must accompany denials (denials=[$(sed -n 's/^denials=//p' "$output_file" | tail -1)], max_denials=[$(sed -n 's/^max_denials=//p' "$output_file" | tail -1)])"
  fi

  if [[ "$ok" == "true" ]] && ! assert_denied_tools_presence "$output_file"; then
    ok=false
    echo "::error::fixture $fixture: denied_tools must be present exactly when denials is (denials=[$(sed -n 's/^denials=//p' "$output_file" | tail -1)], denied_tools present=[$(grep -c '^denied_tools=' "$output_file")])"
  fi

  if [[ "$ok" == "true" ]] && ! assert_kind "$fixture" "$output_file"; then
    ok=false
    echo "::error::fixture $fixture: failure_kind mismatch (want [${expected_kind[$fixture]:-}], got [$(sed -n 's/^failure_kind=//p' "$output_file" | tail -1)])"
  fi

  if [[ "$ok" == "true" ]] && ! assert_log "$fixture" "$log_file"; then
    ok=false
  fi

  if [[ "$ok" == "true" ]]; then
    echo "OK   $fixture (expected $want, exit=$exit_code)"
  else
    echo "::error::fixture $fixture: expected $want but got exit=$exit_code"
    echo "--- script output ---"
    cat "$log_file"
    echo "--- GITHUB_OUTPUT ---"
    cat "$output_file"
    failures=$((failures + 1))
  fi
  rm -f "$output_file" "$log_file"
done

# Explicit non-existent file test (action short-circuit / missing execution file; gha#368)
output_file="$(mktemp)"
set +e
GITHUB_OUTPUT="$output_file" bash "$check_script" "$fixtures_dir/nonexistent-file.json" >/dev/null 2>&1
exit_code=$?
set -e
if [[ "$exit_code" -ne 0 ]] && grep -q '^action_short_circuit=true$' "$output_file" && grep -q '^no_execution_file=true$' "$output_file"; then
  echo "OK   nonexistent-file.json (expected fail-short-circuit, exit=$exit_code)"
else
  echo "::error::nonexistent-file.json did not report action_short_circuit=true and no_execution_file=true"
  failures=$((failures + 1))
fi
rm -f "$output_file"

# gha#540: the denied-command sample redacts token-shaped literals, because
# Actions masks a configured `secrets.*` value in a run log but not a
# credential the agent constructed itself.
#
# This fixture is BUILT HERE rather than committed, and the token is assembled
# from fragments rather than written out, because `check-secrets` scans this
# repo's own history -- a realistic dummy token in a committed file would trip
# that scan forever after, and no amount of later deletion undoes the commit
# that introduced it (see CLAUDE.md's "Its fixtures carry no credential-shaped
# strings, deliberately"). Generating it at test time is the same rule the
# `test-coverage` R-package fixture follows, applied to the one input that
# cannot be committed at all.
# Each credential shape gets its OWN run rather than sharing one fixture,
# because the sample quotes one entry per tool GROUP capped at three groups --
# so several denials sharing a tool name would leave all but the first unquoted,
# and the assertion would pass without the pattern ever being exercised. That is
# the vacuous-assertion shape this suite has already been caught by twice.
#
# Every secret is assembled from fragments at run time and none is committed:
# `check-secrets` scans this repo's own history, so a credential-shaped literal
# in a committed file trips that scan permanently, and deleting the file later
# does not reach the commit that introduced it.
#
# The four shapes below the first two were added in gha#548 review round 2,
# each measured leaking before the fix and redacted after. gha#543 is what made
# them matter: this string now reaches an unmasked PR comment, where Actions'
# secret masking -- the backstop that made GitHub-only coverage defensible when
# the destination was a run log -- does not apply at all.
_ghp="ghp_$(printf 'A%.0s' {1..36})"
_ant="sk-ant-$(printf 'B%.0s' {1..40})"
_finegrained="github_pat_$(printf 'C%.0s' {1..30})"
_opaque="Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MA=="
_hexpat="$(printf 'a1b2c3d4%.0s' {1..5})"
_urlpw="s3cr3tpassw0rdvalue"
# The "@" is assembled at run time for the same reason the credentials are,
# one layer over: `check-phi` runs across this repo's tree with the email
# detector on, and a committed `<word>@<host>.<tld>` literal is email-shaped
# whether or not it is a real address -- so the userinfo case below tripped
# that job even though every secret in it is generated. Splitting the "@" out
# keeps the committed file free of the shape, without blinding the phi scan to
# this whole directory via paths-ignore. Measured: reproduced locally with
# CI's own full detector set, fixed, re-run clean.
_at="@"

# label | secret that must not appear | the denied command carrying it
redaction_cases=(
  # These two carry their credential in a form NO other pattern can reach: not
  # an Authorization header (the generic backstop would catch it) and not URL
  # userinfo (the userinfo pattern would).
  # Written that way, the generic header backstop below catches them, so
  # deleting the vendor-prefix pattern they exist to test leaves the assertion
  # passing -- confirmed by mutation, which is how this exact confound was
  # caught here after being caught once already in a by-hand check. A test for
  # pattern X must be reachable ONLY by pattern X.
  "modern GitHub PAT|$_ghp|printf %s $_ghp > /tmp/token.txt"
  "Anthropic key|$_ant|ANTHROPIC_API_KEY=$_ant python3 probe.py"
  # Pre-existing pattern, previously untested -- the mutation sweep that
  # isolated the new shapes found it had no case at all, so deleting it turned
  # nothing red.
  "fine-grained GitHub PAT|$_finegrained|printf %s $_finegrained > /tmp/pat.txt"
  "lowercase scheme|$_opaque|curl -H 'authorization: bearer $_opaque' https://api.example.com"
  "uppercase header|$_opaque|curl -H 'AUTHORIZATION: Bearer $_opaque' https://api.example.com"
  "token scheme, legacy 40-hex PAT|$_hexpat|curl -H 'Authorization: token $_hexpat' https://api.github.com/x"
  "URL userinfo|$_urlpw|git clone https://alice:${_urlpw}${_at}github.com/o/r.git"
)

for case in "${redaction_cases[@]}"; do
  IFS='|' read -r label secret command <<< "$case"
  fixture="$(mktemp)"; output_file="$(mktemp)"; log_file="$(mktemp)"
  cat > "$fixture" <<REDACTION_FIXTURE
[
  {"type": "system", "subtype": "init"},
  {"type": "assistant", "message": {"content": [{"type": "text",
    "text": "A tool call was denied while fetching the diff."}]}},
  {"type": "result", "subtype": "success", "is_error": false,
   "num_turns": 9, "duration_ms": 60000, "total_cost_usd": 1.5,
   "permission_denials": [
     {"tool_name": "Bash", "tool_use_id": "toolu_1",
      "tool_input": {"command": "$command"}}
   ]}
]
REDACTION_FIXTURE
  set +e
  GITHUB_OUTPUT="$output_file" bash "$check_script" "$fixture" >"$log_file" 2>&1
  set -e
  if grep -qF "$secret" "$log_file"; then
    echo "::error::redaction ($label): the credential reached the log unredacted"
    grep -i 'Denied tools' "$log_file" || cat "$log_file"
    failures=$((failures + 1))
  elif ! grep -qF '***' "$log_file"; then
    echo "::error::redaction ($label): expected a '***' marker in the denied-command sample; log said:"
    grep -i 'Denied tools' "$log_file" || cat "$log_file"
    failures=$((failures + 1))
  else
    echo "OK   <runtime redaction: $label>"
  fi
  rm -f "$fixture" "$output_file" "$log_file"
done

# gha#804: the quota message takes the same path to a PR comment, and the
# door-rejection branch is exactly where the SDK quotes credential context
# (CLAUDE.md's gha#686 entry records a real one). Built at run time for the
# same reason the cases above are: nothing credential-shaped is committed.
# Both destinations are asserted -- the ::warning:: line in the log and the
# quota_message output -- since the comment is composed from the second.
fixture="$(mktemp)"; output_file="$(mktemp)"; log_file="$(mktemp)"
cat > "$fixture" <<QUOTA_REDACTION_FIXTURE
[
  {"type": "system", "subtype": "init"},
  {"type": "result", "subtype": "error_during_execution", "is_error": true,
   "num_turns": 1, "duration_ms": 900, "total_cost_usd": 0,
   "result": "Invalid Authorization header value: Bearer $_ant was rejected"}
]
QUOTA_REDACTION_FIXTURE
set +e
GITHUB_OUTPUT="$output_file" bash "$check_script" "$fixture" >"$log_file" 2>&1
set -e
# Both quota paths publish the message, so both are pinned: the door case
# above and the mid-run 429 below. Removing `| redact` from either extraction
# alone left the suite green until the second case existed. The assertion
# parses the output the way assert_skip does rather than anchoring on the
# key=value wire form, so moving that write to the delimiter form later would
# not fail it for a reason unrelated to redaction.
fixture_mid="$(mktemp)"; output_mid="$(mktemp)"; log_mid="$(mktemp)"
cat > "$fixture_mid" <<QUOTA_MIDRUN_REDACTION_FIXTURE
[
  {"type": "system", "subtype": "init"},
  {"type": "assistant", "message": {"content": [{"type": "text",
    "text": "Reading the diff before the limit hit."}]}},
  {"type": "result", "subtype": "success", "is_error": true, "api_error_status": 429,
   "num_turns": 7, "duration_ms": 90000, "total_cost_usd": 2.5,
   "result": "Rate limited while sending Bearer $_ant; resets at 10pm (UTC)"}
]
QUOTA_MIDRUN_REDACTION_FIXTURE
set +e
GITHUB_OUTPUT="$output_mid" bash "$check_script" "$fixture_mid" >"$log_mid" 2>&1
set -e
redacted_door="$(sed -n 's/^quota_message=//p' "$output_file" | tail -1)"
redacted_mid="$(sed -n 's/^quota_message=//p' "$output_mid" | tail -1)"
if grep -qF "$_ant" "$log_file" "$output_file" "$log_mid" "$output_mid"; then
  echo "::error::redaction (quota message): the credential reached the log or the quota_message output unredacted"
  failures=$((failures + 1))
elif [[ "$redacted_door" != 'Invalid Authorization header value: Bearer *** was rejected' ]]; then
  echo "::error::redaction (quota message, door): expected the redacted message; got '$redacted_door'"
  failures=$((failures + 1))
elif [[ "$redacted_mid" != 'Rate limited while sending Bearer ***; resets at 10pm (UTC)' ]]; then
  echo "::error::redaction (quota message, mid-run 429): expected the redacted message; got '$redacted_mid'"
  failures=$((failures + 1))
else
  echo "OK   <runtime redaction: quota message (door and mid-run)>"
fi
rm -f "$fixture" "$output_file" "$log_file" "$fixture_mid" "$output_mid" "$log_mid"

# The counterweight. Redaction that ate the diagnostic would pass every
# assertion above while destroying the thing gha#540 added the names for, so
# pin that an ordinary denied command survives untouched.
fixture="$(mktemp)"; output_file="$(mktemp)"; log_file="$(mktemp)"
cat > "$fixture" <<'BENIGN_FIXTURE'
[
  {"type": "system", "subtype": "init"},
  {"type": "assistant", "message": {"content": [{"type": "text",
    "text": "A tool call was denied while fetching the diff."}]}},
  {"type": "result", "subtype": "success", "is_error": false,
   "num_turns": 9, "duration_ms": 60000, "total_cost_usd": 1.5,
   "permission_denials": [
     {"tool_name": "Bash", "tool_use_id": "toolu_1",
      "tool_input": {"command": "gh pr diff 548 --repo Morrison-Lab/gha"}}
   ]}
]
BENIGN_FIXTURE
set +e
GITHUB_OUTPUT="$output_file" bash "$check_script" "$fixture" >"$log_file" 2>&1
set -e
if ! grep -qF 'gh pr diff 548 --repo Morrison-Lab/gha' "$log_file"; then
  echo "::error::redaction over-reached: a benign denied command was altered"
  grep -i 'Denied tools' "$log_file" || cat "$log_file"
  failures=$((failures + 1))
else
  echo "OK   <runtime redaction: benign command survives>"
fi
rm -f "$fixture" "$output_file" "$log_file"

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of ${#expected[@]} fixture(s) did not behave as expected"
  exit 1
fi
echo "All ${#expected[@]} fixtures behaved as expected."
