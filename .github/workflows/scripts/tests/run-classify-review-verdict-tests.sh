#!/usr/bin/env bash
# Offline unit tests for classify-review-verdict.sh (gha#767).
#
# Usage: run-classify-review-verdict-tests.sh
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLASSIFIER="$SCRIPTS_DIR/classify-review-verdict.sh"

if [[ ! -x "$CLASSIFIER" && ! -f "$CLASSIFIER" ]]; then
  echo "Error: $CLASSIFIER not found." >&2
  exit 1
fi

passed=0
failed=0

run_test() {
  local name="$1"
  local review_text="$2"
  local expected_clean="$3"
  local expected_verdict="$4"

  local tmp_file
  tmp_file="$(mktemp)"
  printf '%s' "$review_text" > "$tmp_file"

  local out_file
  out_file="$(mktemp)"

  GITHUB_OUTPUT="$out_file" bash "$CLASSIFIER" "$tmp_file" > /dev/null

  local actual_clean
  actual_clean="$(grep -E '^clean=' "$out_file" | cut -d= -f2 || true)"
  local actual_verdict
  actual_verdict="$(grep -E '^verdict=' "$out_file" | cut -d= -f2 || true)"

  rm -f "$tmp_file" "$out_file"

  if [[ "$actual_clean" == "$expected_clean" && "$actual_verdict" == "$expected_verdict" ]]; then
    (( passed++ )) || true
  else
    echo "FAIL: $name (expected clean=$expected_clean verdict=$expected_verdict, got clean=$actual_clean verdict=$actual_verdict)" >&2
    (( failed++ )) || true
  fi
}

echo "Running classify-review-verdict tests..."

# Test 1: Standard Ready for merge
run_test "Standard Ready for merge" \
"## Code Review

Everything looks good.

### Verdict

**Ready for merge** — no blocking findings." \
"true" "ready-for-merge"

# Test 2: Ready for merge with trailing period
run_test "Ready for merge with period" \
"## Code Review

### Verdict

**Ready for merge.**" \
"true" "ready-for-merge"

# Test 3: Ready for merge plain text
run_test "Ready for merge plain text" \
"### Verdict

Ready for merge" \
"true" "ready-for-merge"

# Test 4: Verdict: Ready for merge (label style)
run_test "Verdict label style" \
"## Review

**Verdict:** Ready for merge." \
"true" "ready-for-merge"

# Test 5: Clean verdict
run_test "Clean verdict" \
"### Verdict

**Clean** — diff verified." \
"true" "clean"

# Test 6: Approved verdict
run_test "Approved verdict" \
"### Verdict

**Approved**" \
"true" "approved"

# Test 7: Needs more work
run_test "Needs more work" \
"## Findings
- foo.py:10 bug

### Verdict

**Needs more work** — one actionable bug." \
"false" "needs-more-work"

# Test 8: Changes requested
run_test "Changes requested" \
"### Verdict

**Changes requested**" \
"false" "changes-requested"

# Test 9: Blocked on human review
run_test "Blocked verdict" \
"### Verdict

**Blocked on human review**" \
"false" "blocked"

# Test 10: Impasse / Deadlock
run_test "Impasse verdict" \
"### Verdict

**Impasse** — deadlock between agent suggestions." \
"false" "impasse"

# Test 11: Ready for merge citing past Needs more work
run_test "Ready for merge citing past round" \
"## Review

In round 1 I gave a **Needs more work** verdict. All concerns are now fixed.

### Verdict

**Ready for merge** — all prior findings resolved." \
"true" "ready-for-merge"

# Test 12: Empty file
run_test "Empty review file" \
"" \
"false" "no-output"

# Test 13: Whitespace only
run_test "Whitespace review file" \
"   
   
" \
"false" "no-output"

# Test 14: Review with no verdict header
run_test "No verdict header" \
"## Code Review

Looks okay I guess." \
"false" "no-verdict"

# Test 15: Unrecognized verdict
run_test "Unrecognized verdict" \
"### Verdict

Maybe later" \
"false" "unrecognized"

# Test 16: Fixture text: genuine finished review
run_test "Fixture: genuine finished review" \
"## Code review

No blocking issues found — the diff is small and self-contained.

### Verdict

**Ready for merge.**" \
"true" "ready-for-merge"

# Test 17: Fixture text: verdict-label-format
run_test "Fixture: verdict label format" \
"## Code review

No blocking issues found.

**Verdict:** Ready for merge." \
"true" "ready-for-merge"

# Test 18: Fixture text: verdict-split-across-blocks
run_test "Fixture: verdict split across blocks" \
"## Review of the diff

The frobnicator rename is sound; the boundary case at line 42 is handled by the new guard, and the docs match the shipped behavior.

### Verdict
Ready for merge - no blocking findings.

One follow-up: the instrument re-run also exits 0, so no check has failed (verified above). My verdict stands unchanged:

Verdict: Ready for merge.

**Stopping Point**: Clean stopping point reached -- review posted." \
"true" "ready-for-merge"

# Test 19: Fixture text: verdict-via-gh-comment-heredoc
run_test "Fixture: verdict via gh comment heredoc (Needs more work)" \
"## Code review

One real finding on line 12.

### Verdict

**Needs more work**" \
"false" "needs-more-work"

# Test 20: Fixture text: quota-exhausted-midrun-with-verdict
run_test "Fixture: quota exhausted midrun with verdict" \
"### Verdict

**Ready for merge** — no blocking findings." \
"true" "ready-for-merge"

echo "classify-review-verdict tests: $passed passed, $failed failed."

if (( failed > 0 )); then
  exit 1
fi
exit 0
