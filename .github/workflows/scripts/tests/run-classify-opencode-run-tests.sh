#!/usr/bin/env bash
# Offline table tests for classify-opencode-run.sh (gha#586).
#
# Mirrors the structure of run-classify-gemini-failure-tests.sh: a table of
# (exit-code, stdout-bytes, expected kind, expected headline substrings,
# forbidden substrings) cases plus contract-shape assertions, so the
# classification logic is exercised without a live opencode run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLASSIFY="$SCRIPT_DIR/../classify-opencode-run.sh"

pass=0
fail=0

# assert_case <exit> <bytes> <expected-kind> <headline-substr-regex> [forbidden-regex]
assert_case() {
  local exit_code=$1 bytes=$2 want_kind=$3 headline_re=$4 forbidden_re=${5:-}
  local out
  if ! out=$(bash "$CLASSIFY" "$exit_code" "$bytes" 2>&1); then
    echo "FAIL: ($exit_code, $bytes): classifier exited non-zero:" >&2
    echo "$out" >&2
    fail=$((fail + 1))
    return
  fi
  local got_kind headline
  got_kind=$(sed -n '1s/^kind=//p' <<<"$out")
  headline=$(sed -n '2s/^headline=//p' <<<"$out")
  if [[ "$got_kind" != "$want_kind" ]]; then
    echo "FAIL: ($exit_code, $bytes): kind '$got_kind', expected '$want_kind'" >&2
    fail=$((fail + 1))
    return
  fi
  if [[ -z "$headline" ]]; then
    echo "FAIL: ($exit_code, $bytes): empty headline" >&2
    fail=$((fail + 1))
    return
  fi
  if [[ "$headline" =~ $headline_re ]]; then :; else
    echo "FAIL: ($exit_code, $bytes): headline '$headline' does not match /$headline_re/" >&2
    fail=$((fail + 1))
    return
  fi
  if [[ -n "$forbidden_re" && "$headline" =~ $forbidden_re ]]; then
    echo "FAIL: ($exit_code, $bytes): headline '$headline' must not match /$forbidden_re/" >&2
    fail=$((fail + 1))
    return
  fi
  # The failure marker phrase is load-bearing: classify-review-delivery.sh
  # recognizes a failed run by it. Every failed kind must carry it.
  if [[ "$want_kind" == "failed" ]] && [[ "$headline" != *"OpenCode review failed:"* ]]; then
    echo "FAIL: ($exit_code, $bytes): failed-kind headline lacks the 'OpenCode review failed:' marker" >&2
    fail=$((fail + 1))
    return
  fi
  pass=$((pass + 1))
}

# --- happy path ---------------------------------------------------------
assert_case 0 5000 'review' 'completed\.'

# --- empty output on success --------------------------------------------
assert_case 0 0 'failed' 'produced no review'

# --- non-zero exits ------------------------------------------------------
assert_case 1 0 'failed' 'exited 1'
assert_case 127 0 'failed' 'exited 127'
# Output present but exit non-zero: still a failure -- an incomplete run's
# stdout is unreliable and is surfaced in the comment body, not trusted.
assert_case 1 9999 'failed' 'exited 1'

# --- bad arguments are refused, not classified ---------------------------
if bash "$CLASSIFY" >/dev/null 2>&1; then
  echo "FAIL: missing arguments should be rejected with a non-zero exit" >&2
  fail=$((fail + 1))
else
  pass=$((pass + 1))
fi
if bash "$CLASSIFY" abc 100 >/dev/null 2>&1; then
  echo "FAIL: non-numeric exit code should be rejected with a non-zero exit" >&2
  fail=$((fail + 1))
else
  pass=$((pass + 1))
fi
if bash "$CLASSIFY" 0 xyz >/dev/null 2>&1; then
  echo "FAIL: non-numeric byte count should be rejected with a non-zero exit" >&2
  fail=$((fail + 1))
else
  pass=$((pass + 1))
fi

# --- output contract shape ----------------------------------------------
out=$(bash "$CLASSIFY" 3 42)
line_count=$(wc -l <<<"$out")
if [[ "$line_count" -ge 4 ]]; then
  pass=$((pass + 1))
else
  echo "FAIL: expected at least 4 contract lines (kind/headline/blank/advice), got $line_count" >&2
  fail=$((fail + 1))
fi
if [[ "$(sed -n '3p' <<<"$out")" == "" ]]; then
  pass=$((pass + 1))
else
  echo "FAIL: line 3 of the contract should be blank, got '$(sed -n '3p' <<<"$out")'" >&2
  fail=$((fail + 1))
fi

echo "run-classify-opencode-run-tests: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
