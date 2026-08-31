#!/usr/bin/env bash
# Offline table tests for pack-review-payload.sh (gha#580).
#
# The posting job branches on payload.json keys and on whether the sidecar
# files exist, so this suite pins that contract rather than the JSON's exact
# pretty-print. Two mutations are confirmed to turn it red: dropping a
# required key, and writing review.txt when REVIEW_TEXT_FILE is unset
# (which would make an absent review look like a present empty one).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACK="$SCRIPT_DIR/../pack-review-payload.sh"

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

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

# --- happy path: review text and denied_tools both present -----------------
review="$tmpdir/review.txt"
printf '### Verdict\n\nReady for merge.\n' > "$review"
denied='Taskx6 Bash(gh pr merge 1)'
dir="$tmpdir/happy"
PAYLOAD_DIR="$dir" \
  PR_NUMBER=12 REPO=Morrison-Lab/gha RUN_URL=https://example.invalid/run \
  RUN_ID=99 EVENT_NAME=pull_request CALLER_WF_PATH=.github/workflows/claude-review.yml \
  WF_PATH=.github/workflows/claude-review.yml SELF_MOD=false \
  QUOTA_EXHAUSTED=false CANCELLED=false RESOLVE_OUTCOME=success \
  HEAD_SHA=abc123 TOTAL_COST_USD=1.25 FAILURE_KIND= \
  DENIALS=0 DENIED_TOOLS="$denied" MAX_DENIALS=5 ATTEMPTS=1 \
  TRACK_PROGRESS=false REPORT_COST=true REVIEW_TEXT_FILE="$review" \
  bash "$PACK"
check "happy: payload.json exists" "true" "$([[ -f $dir/payload.json ]] && echo true || echo false)"
check "happy: review.txt copied" "true" "$([[ -f $dir/review.txt ]] && echo true || echo false)"
check "happy: denied_tools.txt copied" "true" "$([[ -f $dir/denied_tools.txt ]] && echo true || echo false)"
check "happy: review_present" "true" "$(jq -r .review_present "$dir/payload.json")"
check "happy: pr_number" "12" "$(jq -r .pr_number "$dir/payload.json")"
check "happy: schema_version" "1" "$(jq -r .schema_version "$dir/payload.json")"
check "happy: denied_tools sidecar is verbatim" "$denied" "$(cat "$dir/denied_tools.txt")"
check "happy: review sidecar is verbatim" "$(cat "$review")" "$(cat "$dir/review.txt")"

# A missing key is a pack bug. Pin the set so adding a posting-job branch
# without packing the field it reads turns this red once the test is updated
# to expect the new key -- and so deleting a key the posting job already
# reads turns it red now.
# tr -d '\r' strips carriage returns for test portability on Windows environments.
keys="$(jq -r 'keys[]' "$dir/payload.json" | tr -d '\r' | sort | tr '\n' ',')"
check "happy: key set" \
  "attempts,caller_wf_path,cancelled,denials,event_name,failure_kind,head_sha,max_denials,pr_number,quota_exhausted,repo,report_cost,resolve_outcome,review_present,run_id,run_url,schema_version,self_mod,skip_notice_posted,total_cost_usd,track_progress,wf_path," \
  "$keys"
check "happy: denied_tools sidecar ends in newline" "" "$(tail -c1 "$dir/denied_tools.txt")"

# --- round-trip: reader's heredoc emit terminates correctly (gha#764) --------
emit_heredoc() {
  local sidecar="$1"
  local delim="eof_test"
  echo "denied_tools<<${delim}"
  if [[ -f "$sidecar" ]]; then
    cat "$sidecar"
    [[ -n "$(tail -c1 "$sidecar")" ]] && echo
  fi
  echo "${delim}"
}

# (a) packed sidecar (has trailing newline from pack-review-payload.sh)
heredoc_out="$(emit_heredoc "$dir/denied_tools.txt")"
check "round-trip: packed sidecar delimiter on its own line" "1" "$(grep -c '^eof_test$' <<<"$heredoc_out")"

# (b) legacy / external sidecar with NO trailing newline
no_nl="$tmpdir/no_newline_denied.txt"
printf '%s' 'Taskx4 (sample: Task: CLAUDE.md compliance review A)' > "$no_nl"
heredoc_no_nl="$(emit_heredoc "$no_nl")"
check "round-trip: un-newlined sidecar delimiter on its own line" "1" "$(grep -c '^eof_test$' <<<"$heredoc_no_nl")"
check "round-trip: un-newlined sidecar value intact" "Taskx4 (sample: Task: CLAUDE.md compliance review A)" "$(sed -n '2p' <<<"$heredoc_no_nl")"

# --- no review text: sidecar omitted, review_present false -----------------
dir="$tmpdir/no-review"
PAYLOAD_DIR="$dir" PR_NUMBER=1 bash "$PACK"
check "no-review: review.txt absent" "false" "$([[ -f $dir/review.txt ]] && echo true || echo false)"
check "no-review: denied_tools.txt absent" "false" "$([[ -f $dir/denied_tools.txt ]] && echo true || echo false)"
check "no-review: review_present false" "false" "$(jq -r .review_present "$dir/payload.json")"
check "no-review: empty pr_number stays a key" "1" "$(jq -r .pr_number "$dir/payload.json")"

# --- missing PAYLOAD_DIR is an error, not a write to cwd -------------------
if PAYLOAD_DIR= bash "$PACK" >/dev/null 2>"$tmpdir/err"; then
  check "missing PAYLOAD_DIR must fail" "fail" "pass"
else
  check "missing PAYLOAD_DIR must fail" "fail" "fail"
fi
check_contains_err="$(grep -c 'PAYLOAD_DIR is required' "$tmpdir/err" || true)"
check "missing PAYLOAD_DIR names the input" "1" "$check_contains_err"

# --- REVIEW_TEXT_FILE pointing at a missing path is "not recorded" --------
dir="$tmpdir/missing-review"
PAYLOAD_DIR="$dir" REVIEW_TEXT_FILE="$tmpdir/does-not-exist" bash "$PACK"
check "missing review file: no sidecar" "false" "$([[ -f $dir/review.txt ]] && echo true || echo false)"
check "missing review file: review_present false" "false" "$(jq -r .review_present "$dir/payload.json")"

# --- denied_tools with quotes and dollars survives jq --arg ----------------
dir="$tmpdir/metachar"
PAYLOAD_DIR="$dir" DENIED_TOOLS='Bash(echo "$(gh pr merge)")' bash "$PACK"
check "metachar denied_tools" 'Bash(echo "$(gh pr merge)")' "$(cat "$dir/denied_tools.txt")"

if [[ "$failures" -ne 0 ]]; then
  echo "::error::$failures/$checks pack-review-payload assertion(s) failed"
  exit 1
fi
echo "All $checks pack-review-payload assertions passed."
