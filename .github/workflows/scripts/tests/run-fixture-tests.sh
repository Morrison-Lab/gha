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
  # gha#540: a mixed-tool, high-count denial array -- the case the count alone
  # cannot explain. Its outcome is the same `fail` as the fixture above; what
  # it exists to pin is the LOG, via must_log below.
  [permission-denials-mixed-tools.json]=fail
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
declare -A must_not_contain=(
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
)
declare -A must_not_log=(
  # The redaction case is NOT here -- it is generated at runtime below, since a
  # committed credential-shaped literal would trip the `secrets` job's own
  # history scan forever after.
  # A clean run must not gain a "Denied tools:" line at all -- the summary is
  # a diagnostic for denials, not noise on every review.
  [genuine-finished-review.json]='Denied tools'
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
  [stub-pr171-waiting-background-agents.json]=0.05
  [stub-pr171-remaining-review-agents.json]=0.08
  [stub-sparta590-scheduled-wakeup.json]=0.03
  [stub-sparta590-unnecessary-call.json]=0.03
  [stub-gha198-high-denial-count.json]=2.2062398500000007
  [empty-review-text.json]=0.01
  [is-error-result.json]=0.15
  [is-error-success-with-verdict.json]=6.23
  [is-error-success-no-verdict.json]=0.97
  [is-error-success-denied-comment-null-denials.json]=1.1
  [denied-comment-null-denials-not-trusted.json]=1.1
  [quota-exhausted.json]=0
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
  if [[ -n "${must_not_contain[$fixture]:-}" ]] && grep -qF "${must_not_contain[$fixture]}" "$posted_file"; then
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

assert_skip() {
  local exit_code="$1" output_file="$2"
  [[ "$exit_code" -eq 0 ]] && grep -q '^quota_exhausted=true$' "$output_file"
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
    skip) assert_skip "$exit_code" "$output_file" && ok=true ;;
    *) echo "::error::unknown expected outcome '$want' for fixture $fixture"; exit 1 ;;
  esac

  if [[ "$ok" == "true" ]] && ! assert_cost "$fixture" "$output_file"; then
    ok=false
    echo "::error::fixture $fixture: total_cost_usd mismatch (want ${expected_cost[$fixture]}, got $(sed -n 's/^total_cost_usd=//p' "$output_file"))"
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
redaction_fixture="$(mktemp)"
# Only the 4-character prefix is a literal; the 36-character body -- the part
# that makes a string token-SHAPED rather than merely token-prefixed -- is
# generated, so nothing matching a credential pattern is ever committed.
fake_token="ghp_$(printf 'A%.0s' {1..36})"
cat > "$redaction_fixture" <<REDACTION_FIXTURE
[
  {"type": "system", "subtype": "init"},
  {"type": "assistant", "message": {"content": [{"type": "text",
    "text": "A tool call was denied while fetching the diff."}]}},
  {"type": "result", "subtype": "success", "is_error": false,
   "num_turns": 9, "duration_ms": 60000, "total_cost_usd": 1.5,
   "permission_denials": [
     {"tool_name": "Bash", "tool_use_id": "toolu_1",
      "tool_input": {"command": "curl -H 'Authorization: Bearer ${fake_token}' https://api.github.com/x"}}
   ]}
]
REDACTION_FIXTURE
output_file="$(mktemp)"
log_file="$(mktemp)"
set +e
GITHUB_OUTPUT="$output_file" bash "$check_script" "$redaction_fixture" >"$log_file" 2>&1
set -e
if grep -qF "$fake_token" "$log_file"; then
  echo "::error::redaction fixture: the denied command's token reached the log unredacted"
  failures=$((failures + 1))
elif ! grep -qF "Bearer ***" "$log_file"; then
  echo "::error::redaction fixture: expected the token to be replaced with '***'; log said:"
  grep -i 'Denied tools' "$log_file" || cat "$log_file"
  failures=$((failures + 1))
else
  echo "OK   <runtime redaction fixture> (token redacted from the denied-command sample)"
fi
rm -f "$redaction_fixture" "$output_file" "$log_file"

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of ${#expected[@]} fixture(s) did not behave as expected"
  exit 1
fi
echo "All ${#expected[@]} fixtures behaved as expected."
