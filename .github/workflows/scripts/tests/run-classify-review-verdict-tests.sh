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

# Test 21: Quoting prior round Needs more work before current Ready for merge verdict
run_test "Quoting prior round Needs more work before Ready for merge" \
"## Code review
The most recent review already covered this diff.
**Verdict:** Needs more work — citing a missing null check on line 42.
That issue has since been fixed in the latest commit.

### Verdict

**Ready for merge** — no blocking findings remain." \
"true" "ready-for-merge"

# Test 22: Quoting prior round Ready for merge before current Needs more work verdict
run_test "Quoting prior round Ready for merge before Needs more work" \
"## Code review
**Verdict:** Ready for merge (prior round).
A new commit introduced a regression at line 88.

### Verdict

**Needs more work** — regression on line 88." \
"false" "needs-more-work"

# Test 23: Trailing sentence starting with Verdict after real verdict section
run_test "Trailing prose starting with Verdict after real verdict section" \
"## Code review

### Verdict

**Ready for merge** — no blocking findings.

Verdict stability across reruns was also checked and confirmed consistent." \
"true" "ready-for-merge"

# Test 24: Trailing commit SHA line after real verdict section
run_test "Trailing Reviewed commit line after real verdict section" \
"## Code review

### Verdict

**Ready for merge** — all checks pass.

Reviewed commit: 1234567890abcdef" \
"true" "ready-for-merge"

# Test 25: Summary sentence before Blocked status line
run_test "Summary sentence before Blocked status line" \
"## Code review

### Verdict

No actionable findings from my review.

Blocked on human review pending a policy decision on scope." \
"false" "blocked"

# Test 26: Prose mentioning Needs more work before real bold Ready for merge status line
run_test "Prose mentioning Needs more work before bold Ready for merge" \
"## Code review

### Verdict

The security concern I raised in the previous round would normally mean Needs more work, but that was already fixed in the latest commit.

**Ready for merge.**" \
"true" "ready-for-merge"

# Test 27: Compound sentence with No actionable findings and blocked
run_test "Compound sentence with No actionable findings and blocked" \
"## Code review

### Verdict

No actionable findings from code review, but this PR is currently blocked pending a human decision." \
"false" "blocked"

# Test 28: Bold Ready for merge followed by unbolded Needs more work correction
run_test "Bold Ready for merge followed by unbolded Needs more work correction" \
"### Verdict

**Ready for merge** — as of my last look.

Wait, I just noticed the tests are still failing, so this actually needs more work." \
"false" "needs-more-work"

# Test 29: Unbolded historical Needs more work followed by unbolded Ready for merge
run_test "Unbolded historical Needs more work followed by unbolded Ready for merge" \
"### Verdict

The prior round said this needs more work, citing line 42. That's since been fixed.

Ready for merge — all clear now." \
"true" "ready-for-merge"

# Test 30: Bold Needs more work followed by unbolded approved
run_test "Bold Needs more work followed by unbolded approved" \
"### Verdict

**Needs more work** — citing missing tests.

Actually, tests were added in the latest commit, so this is approved." \
"true" "approved"

# Test 31: Unbolded Changes requested followed by unbolded clean
run_test "Unbolded Changes requested followed by unbolded clean" \
"### Verdict

Changes requested on line 12.

Update: line 12 fixed. Clean." \
"true" "clean"

# Test 32: Unbolded Ready for merge followed by unbolded changes requested
run_test "Unbolded Ready for merge followed by unbolded changes requested" \
"### Verdict

Ready for merge.

Wait, changes requested." \
"false" "changes-requested"

# Test 33: Compound sentence with blocked followed by ready for merge
run_test "Compound sentence with blocked followed by ready for merge" \
"### Verdict

Although the previous review was blocked, this revision is now ready for merge." \
"true" "ready-for-merge"

# Test 34: Negated ready for merge (Not ready for merge)
run_test "Not ready for merge" \
"### Verdict

Not ready for merge." \
"false" "needs-more-work"

# Test 35: Negated approved (This change is not approved)
run_test "Not approved" \
"### Verdict

This change is not approved." \
"false" "rejected"

# Test 36: Negated clean (The tree is not clean)
run_test "Not clean" \
"### Verdict

The tree is not clean." \
"false" "needs-more-work"

# Test 37: Negated ready to merge (Not ready to merge yet)
run_test "Not ready to merge yet" \
"### Verdict

Not ready to merge yet -- see findings below." \
"false" "needs-more-work"

# Test 38: Incidental passed describing CI results after Needs more work
run_test "Incidental passed describing CI results after Needs more work" \
"### Verdict

This needs more work on line 10. Unrelated: the CI suite passed." \
"false" "needs-more-work"

# Test 39: Never approved
run_test "Never approved" \
"### Verdict

Never approved pending refactoring." \
"false" "rejected"

# Test 40: Negated clean followed by later approved
run_test "Negated clean followed by later approved" \
"### Verdict

Although the working tree was initially not clean, this hotfix is approved." \
"true" "approved"

# Test 41: Bold Passed standalone verdict
run_test "Bold Passed standalone verdict" \
"### Verdict

**Passed** — all criteria met." \
"true" "ready-for-merge"

# Test 42: Not ready followed by ready for merge resolution
run_test "Not ready followed by ready for merge resolution" \
"### Verdict

Initially not ready, but with latest fixes, ready for merge." \
"true" "ready-for-merge"

# Test 43: Contraction isn't ready for merge
run_test "Contraction isn't ready for merge" \
"### Verdict

This isn't ready for merge -- there's still a data race in the new goroutine." \
"false" "needs-more-work"

# Test 44: Contraction isn't clean
run_test "Contraction isn't clean" \
"### Verdict

Honestly, this isn't clean -- there's a leftover debug print on line 9." \
"false" "needs-more-work"

# Test 45: Contraction wasn't approved
run_test "Contraction wasn't approved" \
"### Verdict

This wasn't approved by the security team, pending further review." \
"false" "rejected"

# Test 46: Contraction can't be approved
run_test "Contraction can't be approved" \
"### Verdict

This can't be approved yet given the failing test suite." \
"false" "rejected"

# Test 47: Contraction doesn't look ready
run_test "Contraction doesn't look ready" \
"### Verdict

This doesn't look ready to merge." \
"false" "needs-more-work"

# Test 48: Negated blocking phrase with not blocked
run_test "Negated blocking phrase with not blocked" \
"### Verdict

Ready for merge, not blocked." \
"true" "ready-for-merge"

# Test 49: Negated blocking phrase with never rejected
run_test "Negated blocking phrase with never rejected" \
"### Verdict

This PR was never rejected." \
"true" "ready-for-merge"

# Test 50: Contraction isn't blocked
run_test "Contraction isn't blocked" \
"### Verdict

This isn't blocked, ready for merge." \
"true" "ready-for-merge"

# Test 51: Bold emphasis wrapped around negation word (not ready for merge)
run_test "Bold emphasis wrapped around negation word" \
"### Verdict

This is **not** ready for merge." \
"false" "needs-more-work"

# Test 52: Italic emphasis wrapped around negation word (not approved)
run_test "Italic emphasis wrapped around negation word" \
"### Verdict

*not* approved" \
"false" "rejected"

# Test 53: Underscore emphasis wrapped around negation word (not clean)
run_test "Underscore emphasis wrapped around negation word" \
"### Verdict

_not_ clean" \
"false" "needs-more-work"

# Test 54: Double underscore emphasis around never approved
run_test "Double underscore emphasis around never approved" \
"### Verdict

__never__ approved" \
"false" "rejected"

# Test 55: No longer blocked
run_test "No longer blocked" \
"### Verdict

No longer blocked." \
"true" "ready-for-merge"

# Test 56: No longer needs more work
run_test "No longer needs more work" \
"### Verdict

This PR no longer needs more work." \
"true" "ready-for-merge"

echo "classify-review-verdict tests: $passed passed, $failed failed."

if (( failed > 0 )); then
  exit 1
fi
exit 0
