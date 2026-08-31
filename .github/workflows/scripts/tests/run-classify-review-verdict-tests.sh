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

# Test 57: No longer approved
run_test "No longer approved" \
"### Verdict

This PR is no longer approved after the regression." \
"false" "rejected"

# Test 58: No longer ready for merge
run_test "No longer ready for merge" \
"### Verdict

This is no longer ready for merge given the new failing test." \
"false" "needs-more-work"

# Test 59: No longer clean
run_test "No longer clean" \
"### Verdict

This PR is no longer clean; a regression was introduced." \
"false" "needs-more-work"

# Test 60: Not quite ready to merge
run_test "Not quite ready to merge" \
"### Verdict

Not quite ready to merge -- one issue remains." \
"false" "needs-more-work"

# Test 61: Not fully approved
run_test "Not fully approved" \
"### Verdict

Not fully approved; see the note on line 20." \
"false" "rejected"

# Test 62: Not really clean
run_test "Not really clean" \
"### Verdict

Not really clean given the leftover debug code." \
"false" "needs-more-work"

# Test 63: Comma parenthetical after negator (not, in my honest opinion, ready for merge)
run_test "Comma parenthetical after negator (not, in my honest opinion, ready for merge)" \
"### Verdict

This is not, in my honest opinion, ready for merge." \
"false" "needs-more-work"

# Test 64: Comma parenthetical with long hedge (not, after a very careful and thorough review, approved)
run_test "Comma parenthetical with long hedge (not, after a very careful and thorough review, approved)" \
"### Verdict

This PR is not, after a very careful and thorough review, approved." \
"false" "rejected"

# Test 65: No longer with comma parenthetical (no longer, in any sense, clean)
run_test "No longer with comma parenthetical (no longer, in any sense, clean)" \
"### Verdict

Given the regression, this is no longer, in any sense, clean." \
"false" "needs-more-work"

# Test 66: Negator followed by however (not, however, ready for merge)
run_test "Negator followed by however (not, however, ready for merge)" \
"### Verdict

This is not, however, ready for merge." \
"false" "needs-more-work"

# Test 67: 4-word gap without punctuation (not currently under any circumstances ready for merge)
run_test "4-word gap without punctuation (not currently under any circumstances ready for merge)" \
"### Verdict

This is not currently under any circumstances ready for merge." \
"false" "needs-more-work"

# Test 68: Parenthetical with concessive word (not, although it looks fine on the surface, ready for merge)
run_test "Parenthetical with concessive word (not, although it looks fine on the surface, ready for merge)" \
"### Verdict

This is not, although it looks fine on the surface, ready for merge." \
"false" "needs-more-work"

# Test 69: No longer with concessive word parenthetical (no longer, although once true, blocked)
run_test "No longer with concessive word parenthetical (no longer, although once true, blocked)" \
"### Verdict

This PR is no longer, although once true, blocked." \
"true" "ready-for-merge"

# Test 70: 7+ word gap without punctuation (not by any reasonable measure or standard currently ready for merge)
run_test "7+ word gap without punctuation (not by any reasonable measure or standard currently ready for merge)" \
"### Verdict

This is not by any reasonable measure or standard currently ready for merge." \
"false" "needs-more-work"

# Test 71: 7+ word gap without punctuation for clean (not under any possible definition or metric clean)
run_test "7+ word gap without punctuation for clean (not under any possible definition or metric clean)" \
"### Verdict

This is not under any possible definition or metric clean." \
"false" "needs-more-work"

# Test 72: Parentheses delimiter (not (yet) ready for merge)
run_test "Parentheses delimiter (not (yet) ready for merge)" \
"### Verdict

This is not (yet) ready for merge." \
"false" "needs-more-work"

# Test 73: Parentheses delimiter (not (yet) approved)
run_test "Parentheses delimiter (not (yet) approved)" \
"### Verdict

This PR is not (yet) approved." \
"false" "rejected"

# Test 74: Em-dash delimiter (not -- at least for now -- ready for merge)
run_test "Em-dash delimiter (not -- at least for now -- ready for merge)" \
"### Verdict

This is not -- at least for now -- ready for merge." \
"false" "needs-more-work"

# Test 75: Semicolon delimiter (not; strictly speaking; ready for merge)
run_test "Semicolon delimiter (not; strictly speaking; ready for merge)" \
"### Verdict

This is not; strictly speaking; ready for merge." \
"false" "needs-more-work"

# Test 76: Independent clause separation with and
run_test "Independent clause separation with and" \
"### Verdict

There is no reason to think the tests were skipped and the reviewer confirms everything is ready for merge." \
"true" "ready-for-merge"

# Test 77: Long natural parenthetical hedge (>60 chars) (not, on balance and after further reflection on the concerns raised earlier in this review, ready for merge)
run_test "Long natural parenthetical hedge (>60 chars)" \
"### Verdict

This is not, on balance and after further reflection on the concerns raised earlier in this review, ready for merge." \
"false" "needs-more-work"

# Test 78: Long unpunctuated hedge (>8 words) without coordinators (not under any conceivable circumstance or criteria ready for merge)
run_test "Long unpunctuated hedge (>8 words) without coordinators" \
"### Verdict

This is not under any conceivable circumstance or criteria ready for merge." \
"false" "needs-more-work"

# Test 79: Colon delimiter (not: by any measure, ready for merge.)
run_test "Colon delimiter (not: by any measure, ready for merge.)" \
"### Verdict

This is not: by any measure, ready for merge." \
"false" "needs-more-work"

# Test 80: Quote delimiter (not \"in any sense\" ready for merge.)
run_test "Quote delimiter (not \"in any sense\" ready for merge.)" \
"### Verdict

This is not \"in any sense\" ready for merge." \
"false" "needs-more-work"

# Test 81: Unmatched single comma (not, in my honest opinion ready for merge.)
run_test "Unmatched single comma (not, in my honest opinion ready for merge.)" \
"### Verdict

This is not, in my honest opinion ready for merge." \
"false" "needs-more-work"

# Test 82: Unmatched single dash (not - in my honest opinion ready for merge.)
run_test "Unmatched single dash (not - in my honest opinion ready for merge.)" \
"### Verdict

This is not - in my honest opinion ready for merge." \
"false" "needs-more-work"

# Test 83: Unmatched single colon (not: in my honest opinion ready for merge.)
run_test "Unmatched single colon (not: in my honest opinion ready for merge.)" \
"### Verdict

This is not: in my honest opinion ready for merge." \
"false" "needs-more-work"

# Test 84: Unmatched single semicolon (not; in my honest opinion ready for merge.)
run_test "Unmatched single semicolon (not; in my honest opinion ready for merge.)" \
"### Verdict

This is not; in my honest opinion ready for merge." \
"false" "needs-more-work"

# Test 85: Delimited hedge containing but (not, but should be once the failing test is fixed, ready for merge)
run_test "Delimited hedge containing but" \
"### Verdict

This PR is not, but should be once the failing test is fixed, ready for merge." \
"false" "needs-more-work"

# Test 86: Delimited hedge containing whereas (not, whereas prior PRs were, approved)
run_test "Delimited hedge containing whereas" \
"### Verdict

This PR is not, whereas prior PRs were, approved." \
"false" "rejected"

# Test 87: Not yet ready for merge
run_test "Not yet ready for merge" \
"### Verdict

This is not yet ready for merge." \
"false" "needs-more-work"

# Test 88: Not yet approved
run_test "Not yet approved" \
"### Verdict

This is not yet approved." \
"false" "rejected"

# Test 89: Not yet clean
run_test "Not yet clean" \
"### Verdict

This is not yet clean." \
"false" "needs-more-work"

# Test 90: Adversative however separating negated clause from blocked status
run_test "Adversative however separating negated clause from blocked status" \
"### Verdict

This is not fully reviewed however blocked pending legal sign-off." \
"false" "blocked"

# Test 91: Adversative though separating negated clause from blocked status
run_test "Adversative though separating negated clause from blocked status" \
"### Verdict

This is not fully reviewed though blocked pending legal sign-off." \
"false" "blocked"

# Test 92: Adversative still separating negated clause from blocked status
run_test "Adversative still separating negated clause from blocked status" \
"### Verdict

This is not fully reviewed still blocked pending legal sign-off." \
"false" "blocked"

# Test 93: Adversative nonetheless separating negated clause from blocked status
run_test "Adversative nonetheless separating negated clause from blocked status" \
"### Verdict

This is not fully reviewed nonetheless blocked pending legal sign-off." \
"false" "blocked"

# Test 94: Adversative nevertheless separating negated clause from blocked status
run_test "Adversative nevertheless separating negated clause from blocked status" \
"### Verdict

This is not fully reviewed nevertheless blocked pending legal sign-off." \
"false" "blocked"

# Test 95: Concessive however inside negated positive phrase
run_test "Concessive however inside negated positive phrase" \
"### Verdict

This is not fully addressed however ready for merge." \
"false" "needs-more-work"

# Test 96: Concessive though inside negated positive phrase
run_test "Concessive though inside negated positive phrase" \
"### Verdict

This is not fully addressed though ready for merge." \
"false" "needs-more-work"

# Test 97: Concessive still inside negated positive phrase
run_test "Concessive still inside negated positive phrase" \
"### Verdict

This is not fully addressed still ready for merge." \
"false" "needs-more-work"

# Test 98: Concessive nonetheless inside negated positive phrase
run_test "Concessive nonetheless inside negated positive phrase" \
"### Verdict

This is not fully addressed nonetheless ready for merge." \
"false" "needs-more-work"

# Test 99: Concessive nevertheless inside negated positive phrase
run_test "Concessive nevertheless inside negated positive phrase" \
"### Verdict

This is not fully addressed nevertheless ready for merge." \
"false" "needs-more-work"

# Test 100: Unrelated not clause followed by needs more work without punctuation
run_test "Unrelated not clause followed by needs more work without punctuation" \
"### Verdict

The migration script is not idempotent needs more work." \
"false" "needs-more-work"

# Test 101: Unrelated not clause followed by changes requested without punctuation
run_test "Unrelated not clause followed by changes requested without punctuation" \
"### Verdict

This implementation is not thread safe changes requested." \
"false" "changes-requested"

# Test 102: No changes requested
run_test "No changes requested" \
"### Verdict

No changes requested." \
"true" "ready-for-merge"

# Test 103: No changes required
run_test "No changes required" \
"### Verdict

No changes required." \
"true" "ready-for-merge"

# Test 104: Zero changes requested
run_test "Zero changes requested" \
"### Verdict

Zero changes requested." \
"true" "ready-for-merge"

# Test 105: Without changes requested
run_test "Without changes requested" \
"### Verdict

Without changes requested." \
"true" "ready-for-merge"

# Test 106: Conversational No comma before needs more work
run_test "Conversational No comma before needs more work" \
"### Verdict

No, this PR needs more work." \
"false" "needs-more-work"

# Test 107: Conversational No comma before blocked
run_test "Conversational No comma before blocked" \
"### Verdict

No, unfortunately this is blocked pending legal review." \
"false" "blocked"

# Test 108: Conversational No dash before needs more work
run_test "Conversational No dash before needs more work" \
"### Verdict

No -- this needs more work." \
"false" "needs-more-work"

# Test 109: Conversational No colon before needs more work
run_test "Conversational No colon before needs more work" \
"### Verdict

No: this needs more work." \
"false" "needs-more-work"

# Test 110: Conversational No comma before findings
run_test "Conversational No comma before findings" \
"### Verdict

No, this PR has findings." \
"false" "unrecognized"

# Test 111: Conversational No comma before blocking issues
run_test "Conversational No comma before blocking issues" \
"### Verdict

No, this PR still has blocking issues." \
"false" "unrecognized"

# Test 112: Conversational No comma before blockers
run_test "Conversational No comma before blockers" \
"### Verdict

No, this PR has blockers." \
"false" "unrecognized"

# Test 113: Conversational No dash before findings
run_test "Conversational No dash before findings" \
"### Verdict

No -- there are still findings that need addressing." \
"false" "unrecognized"

# Test 114: Conversational No comma before changes requested
run_test "Conversational No comma before changes requested" \
"### Verdict

No, changes requested here." \
"false" "changes-requested"

echo "classify-review-verdict tests: $passed passed, $failed failed."

if (( failed > 0 )); then
  exit 1
fi
exit 0
