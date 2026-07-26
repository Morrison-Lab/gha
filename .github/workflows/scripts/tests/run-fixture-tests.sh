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
  [quota-exhausted.json]=skip
  [verdict-label-format.json]=pass
  [verdict-not-last-block.json]=pass
  [verdict-via-inline-comment-tool.json]=pass
  [verdict-via-gh-comment-heredoc.json]=pass
  [denied-bash-comment-not-trusted.json]=fail-stub
)

# For `pass` fixtures where the posted review_text_file's content matters
# (gha#173): the block it must contain, and a block it must NOT contain.
declare -A must_contain=(
  [verdict-not-last-block.json]='Ready for merge'
  # gha#218 review finding 2: review_text_file must carry the actual
  # verdict-bearing content (from the inline-comment tool's body), not
  # just fall back to the narration text block that happens to satisfy
  # the pass/fail scan.
  [verdict-via-inline-comment-tool.json]='Ready for merge'
  # The review lives inside a `gh pr comment ... <<EOF ... EOF` heredoc body.
  # review_text_file must carry that unwrapped body, not the raw command
  # string (which would post a literal `gh pr comment ...` block to the PR).
  [verdict-via-gh-comment-heredoc.json]='One real finding on line 12'
)
declare -A must_not_contain=(
  [verdict-not-last-block.json]="I've posted my findings"
  [verdict-via-inline-comment-tool.json]="Posted the inline finding and a summary comment ending in"
  [verdict-via-gh-comment-heredoc.json]='gh pr comment'
)

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
  [quota-exhausted.json]=0
  [verdict-label-format.json]=0.31
  [verdict-not-last-block.json]=0.37
  [verdict-via-inline-comment-tool.json]=0.55
  [verdict-via-gh-comment-heredoc.json]=0.61
  [denied-bash-comment-not-trusted.json]=0.4
)

assert_cost() {
  local fixture="$1" output_file="$2"
  local want="${expected_cost[$fixture]}" got
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
    skip) assert_skip "$exit_code" "$output_file" && ok=true ;;
    *) echo "::error::unknown expected outcome '$want' for fixture $fixture"; exit 1 ;;
  esac

  if [[ "$ok" == "true" ]] && ! assert_cost "$fixture" "$output_file"; then
    ok=false
    echo "::error::fixture $fixture: total_cost_usd mismatch (want ${expected_cost[$fixture]}, got $(sed -n 's/^total_cost_usd=//p' "$output_file"))"
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

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of ${#expected[@]} fixture(s) did not behave as expected"
  exit 1
fi
echo "All ${#expected[@]} fixtures behaved as expected."
