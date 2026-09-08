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

# gha#819: the structured review-data payload sits AFTER the verdict heading,
# and the scan is last-match-wins, so one finding word in its JSON prose used
# to override an approving verdict. Measured on gha#811, where
# "concurrency-deadlock audit" inside holistic_assessment scored the review
# `impasse` and failed require-clean-verdict. Both payload spellings this repo
# emits are covered, plus the negative control: a fence is not a blanket
# excuse to ignore text, so a verdict stated only outside one still counts,
# and an unclosed fence must not swallow a later verdict line that precedes it.
run_test "Payload in an HTML comment does not override the verdict" \
"### Verdict

**Ready for merge.**

<!-- review-data:
{\"verdict\": \"CLEAN\", \"holistic_assessment\": \"The concurrency-deadlock audit is sound.\"}
-->" \
"true" "ready-for-merge"

run_test "Payload in a json fence does not override the verdict" \
"### Verdict

**Ready for merge.**

\`\`\`json
{\"verdict\": \"CLEAN\", \"note\": \"the deadlock fix is correct; nothing is blocked\"}
\`\`\`" \
"true" "ready-for-merge"

run_test "A single-line HTML comment is skipped without swallowing the rest" \
"### Verdict

<!-- generated by the reviewer -->
**Ready for merge.**" \
"true" "ready-for-merge"

run_test "A real non-clean verdict outside any payload still counts" \
"### Verdict

**Needs more work.**

<!-- review-data:
{\"verdict\": \"NOT_CLEAN\"}
-->" \
"false" "needs-more-work"

run_test "A tilde-fenced payload does not override the verdict" \
"### Verdict

**Ready for merge.**

~~~
the change is blocked on nothing
~~~" \
"true" "ready-for-merge"

# gha#819 review. Each of these fails against an earlier draft of the fix.
run_test "A verdict heading inside a fence does not win over the real one" \
"### Verdict

**Ready for merge.**

\`\`\`
### Verdict
blocked
\`\`\`" \
"true" "ready-for-merge"

run_test "An inline comment on the verdict line keeps the verdict" \
"### Verdict

**Ready for merge.** <!-- run 123 -->" \
"true" "ready-for-merge"

run_test "A second opener after a closed comment span is still excluded" \
"### Verdict

**Ready for merge.** <!-- a --> tail <!-- review-data:
{\"note\": \"impasse\"}
-->" \
"true" "ready-for-merge"

run_test "Tildes do not close a backtick fence" \
"### Verdict

**Ready for merge.**

\`\`\`
~~~
blocked
\`\`\`" \
"true" "ready-for-merge"

run_test "A shorter run does not close a longer fence" \
"### Verdict

**Ready for merge.**

\`\`\`\`
\`\`\`
rejected
\`\`\`\`" \
"true" "ready-for-merge"

# gha#819 review round 2.
run_test "A comment on the fence opener line does not defeat the fence" \
"### Verdict

**Ready for merge.**

\`\`\`json <!-- x
-->
{\"note\": \"blocked\"}
\`\`\`" \
"true" "ready-for-merge"

run_test "An excised comment span does not fabricate a word boundary" \
"### Verdict

**Ready for<!-- x -->merge.**" \
"false" "unrecognized"

run_test "An empty comment terminates rather than swallowing the rest" \
"### Verdict

**Ready for merge.** <!-->
blocked" \
"false" "blocked"

# --- gha#827: inline code spans are quoted strings, not verdict statements ---
#
# The first case is the measured failure verbatim (Morrison-Lab/ai-config#3154,
# run 33832648873): a backticked identifier after the verdict heading was
# normalised to "NOT CLEAN" and, under last-match-wins, outranked the approving
# line above it. Confirmed to report clean=false verdict=needs-more-work against
# the pre-fix script.
run_test "A backticked NOT_CLEAN after the verdict does not flip it" \
"### Verdict

**Ready for merge**

\`check-pr-fully-clean.py\` reports \`NOT_CLEAN\`, but every blocker is one of the two non-content categories." \
"true" "ready-for-merge"

# The bare identifier, with no backticks at all. This is the strip_emphasis
# half of the fix rather than the code-span half, so it fails if only the span
# pass is added.
run_test "A bare NOT_CLEAN identifier is one token, not a negation" \
"### Verdict

**Ready for merge**

The instrument printed NOT_CLEAN for a base-currency reason only." \
"true" "ready-for-merge"

# The span pass must not INVENT a verdict by closing neighbours up: deleting
# the span outright turns this into "no findings", which the negated-negative
# pattern reads as affirmatively clean. The placeholder is what prevents it.
run_test "A code span between a negator and its target does not fabricate a match" \
"### Verdict

Needs more work: no \`--fail-under\` findings threshold is configured." \
"false" "needs-more-work"

# A closing run must be exactly as long as the opener, so a SINGLE tick inside
# a double-tick span does not close it. The span must therefore contain a
# nested single-tick pair: a plain ``NOT_CLEAN`` fixture passes under a
# close-on-any-run mutation too, because its first following run is already the
# real closer, so it discriminates nothing.
#
# Confirmed: replacing the run-length test with an unconditional close scores
# this clean=true verdict=clean rather than ready-for-merge, because the span
# collapses to nothing and the bare words "not clean" survive into the scan.
run_test "A single tick inside a double-tick span does not close it" \
"### Verdict

**Ready for merge**

The report says \`\` \`not clean\` \`\` only for a base-currency reason." \
"true" "ready-for-merge"

# An unclosed run is left alone rather than swallowing the rest of the review,
# so a real finding after it is still scored.
run_test "An unclosed backtick run does not swallow a later finding" \
"### Verdict

**Ready for merge**

Note the stray \` tick here.
Changes requested on the second pass." \
"false" "changes-requested"

# A heading inside a multi-line span is not a verdict heading. The quoted
# heading must come AFTER the real one, or the case discriminates nothing: with
# span stripping removed the LAST heading still has to be the quoted one for
# last_idx to land in the wrong place. An earlier revision put it first and
# passed with strip_code_spans deleted entirely.
#
# Newline preservation is a separate, unpinned invariant: three fixtures were
# tried against a mutation dropping it and none distinguished them, because the
# output is re-split immediately afterwards. See the note in
# classify-review-verdict.sh.
run_test "A verdict heading inside a multi-line code span does not win" \
"### Verdict

**Ready for merge**

Quoting the shape: \`\` a
### Verdict
b \`\` for reference." \
"true" "ready-for-merge"

# --- gha#827 review: a code span must not cross a blank line ---
#
# A code span is inline content, so CommonMark ends it at the paragraph break.
# Scanning the document as one flat string paired two unrelated stray backticks
# in different paragraphs and blanked everything between them, the real verdict
# heading included. Confirmed to score clean=false verdict=no-verdict before
# the block split was added.
run_test "Stray backticks in separate paragraphs do not pair into a span" \
"A note about the \`foo flag.

### Verdict

**Ready for merge**

See the \`bar setting." \
"true" "ready-for-merge"

# --- gha#827 review: \b before positive_targets ---
#
# pos_gap_pattern ends in \s* and repeats \w+, so without a leading boundary
# the regex backtracks inside a word: "already" splits into the gap word "al"
# plus the target "ready". Distinct root cause from the span blanking -- no
# backticks and no underscore are involved. Confirmed to score
# clean=false verdict=needs-more-work against origin/main.
run_test "The word already does not supply a 'ready' target to a negator" \
"### Verdict

**Ready for merge**

The base was not already current, so I updated it." \
"true" "ready-for-merge"

# A genuine blocking statement in ordinary prose after the verdict still wins.
# Without this, a fix that simply stopped scanning post-verdict prose would
# pass every case above.
run_test "A real rejection in prose after the verdict still wins" \
"### Verdict

**Ready for merge**

On reflection this is blocked until the migration lands." \
"false" "blocked"

# --- gha#827 review: a real NUL byte must not flip a rejection to clean ---
#
# strip_emphasis protects an intra-word underscore with a NUL sentinel and
# swaps it back afterwards, and that swap cannot tell its own sentinel from a
# NUL already present in the text. Before the read-time scrub, a real NUL
# became an underscore, merged "needs<NUL>more" into one \w-class token, and
# scored a genuine rejection ready-for-merge -- the false-CLEAN direction,
# which bypasses require-clean-verdict on a review that said the opposite.
#
# This cannot go through run_test: a bash variable cannot hold a NUL byte, so
# the fixture is written with printf's octal escape instead. The paired control
# is the same body with a space, which must reach the same verdict -- without
# it the case would pass on a script that simply failed to parse the fixture.
run_nul_test() {
  local name="$1" sep="$2" expected_clean="$3" expected_verdict="$4"
  local tmp_file out_file
  tmp_file="$(mktemp)"
  out_file="$(mktemp)"
  printf '### Verdict\n\n**Ready for merge**\n\nOn reflection this needs%bmore work.\n' \
    "$sep" > "$tmp_file"
  GITHUB_OUTPUT="$out_file" bash "$CLASSIFIER" "$tmp_file" > /dev/null
  local actual_clean actual_verdict
  actual_clean="$(grep -E '^clean=' "$out_file" | cut -d= -f2 || true)"
  actual_verdict="$(grep -E '^verdict=' "$out_file" | cut -d= -f2 || true)"
  rm -f "$tmp_file" "$out_file"
  if [[ "$actual_clean" == "$expected_clean" && "$actual_verdict" == "$expected_verdict" ]]; then
    (( passed++ )) || true
  else
    echo "FAIL: $name (expected clean=$expected_clean verdict=$expected_verdict, got clean=$actual_clean verdict=$actual_verdict)" >&2
    (( failed++ )) || true
  fi
}

run_nul_test "A real NUL byte does not flip a rejection to clean" '\000' \
  "false" "needs-more-work"
run_nul_test "Control: the same body with a space is also a rejection" ' ' \
  "false" "needs-more-work"

# --- gha#845: read the review-data payload's own verdict field first ---
#
# The structured review-data payload states its own verdict directly, and a
# machine reader should trust that field rather than re-derive it from the
# prose triage-exemption wording (which the anchored "No action" rule below
# also covers on its own). Measured on sparta#1547 (a scheduled, trivial
# baseline-refresh PR): the review body's "### Verdict" section read "No
# action -- ... does not need code review", which matched none of the old
# clean_kw phrases and scored unrecognized, even though the same comment's
# review-data payload already said "verdict": "CLEAN".
run_test "sparta#1547 shape: payload CLEAN wins even with unfamiliar prose" \
"### Verdict

**No action -- automated, trivial PR that does not need code review** (scheduled benchmark-baseline refresh with no code/behavior change).

<details>
<summary>Review data</summary>

<!-- review-data: {\"schema_version\":\"1.1\",\"reviewer\":\"claude\",\"commit_sha\":\"abc\",\"verdict\":\"CLEAN\",\"findings\":[]} -->

\`\`\`json
{\"schema_version\": \"1.1\", \"reviewer\": \"claude\", \"commit_sha\": \"abc\", \"verdict\": \"CLEAN\", \"findings\": []}
\`\`\`

</details>

Reviewed commit: abc" \
"true" "ready-for-merge"

# Same prose, no review-data block at all: this must classify clean on the
# prose scan alone, independent of the payload fast path above. It passes
# via the line-anchored no_action_anchor check (content_lines[0] starts
# with "no action"), not via "does not need (code )?review" -- that phrase
# was considered and deliberately not added to clean_kw (gha#845 review,
# finding 4, above).
run_test "Triage-exemption prose alone matches the anchored no-action rule" \
"### Verdict

**No action -- automated, trivial PR that does not need code review** (scheduled benchmark-baseline refresh with no code/behavior change)." \
"true" "ready-for-merge"

# The payload wins even when the prose disagrees with it -- e.g. a stale
# caption left over from editing, or prose written before the payload was
# regenerated.
run_test "Payload NOT_CLEAN overrides prose that reads Ready for merge" \
"### Verdict

**Ready for merge**

<!-- review-data: {\"schema_version\":\"1.1\",\"verdict\":\"NOT_CLEAN\"} -->" \
"false" "needs-more-work"

# A malformed payload (not valid JSON) is not a source of truth, so this
# falls back to the ordinary prose scan, same as no payload at all.
run_test "Malformed review-data JSON falls back to the prose scan" \
"### Verdict

**Ready for merge**

<!-- review-data: {this is not json} -->" \
"true" "ready-for-merge"

# A payload with a schema_version but a verdict value that is neither CLEAN
# nor NOT_CLEAN is not authoritative either, so this also falls back to the
# prose scan.
run_test "Payload verdict outside CLEAN/NOT_CLEAN falls back to the prose scan" \
"### Verdict

**Needs more work**

<!-- review-data: {\"schema_version\":\"1.1\",\"verdict\":\"UNKNOWN\"} -->" \
"false" "needs-more-work"

# gha#845 review, finding 4: "does not need (code) review" was removed from
# clean_kw entirely (it has no fixed position in the template, so no anchor
# rules out it appearing in ordinary explanatory prose after a rejection --
# see the "changes requested" cases below). This test still passes, but no
# longer via that removed keyword: its body already STARTS with "No
# action", so the line-anchored no_action_anchor check (applied only to
# content_lines[0], the verdict line itself) is what now classifies it
# clean. Contractions are expanded before that check runs, so the
# contracted "doesn't" form is unaffected either way.
run_test "Contracted does not need code review still matches" \
"### Verdict

**No action, doesn't need code review.**" \
"true" "ready-for-merge"

# --- gha#845 review: payload trusted from a blockquoted or fenced quote ---
#
# The payload scan used to search the raw, unstripped review text, so a
# `<!-- review-data: ... -->` comment someone was merely QUOTING -- inside a
# `> ...` blockquote, or inside a fenced code block -- was trusted as the
# live verdict even though the prose verdict said otherwise. Finding 1.
run_test "A blockquoted stale CLEAN payload does not override Needs more work" \
"### Verdict

**Needs more work** -- one issue remains.

> Earlier this said:
> <!-- review-data: {\"schema_version\":\"1.1\",\"verdict\":\"CLEAN\"} -->" \
"false" "needs-more-work"

run_test "A fenced stale CLEAN payload does not override Needs more work" \
"### Verdict

**Needs more work** -- one issue remains.

\`\`\`
<!-- review-data: {\"schema_version\":\"1.1\",\"verdict\":\"CLEAN\"} -->
\`\`\`" \
"false" "needs-more-work"

# --- gha#845 third review, finding 1: a quoted heading/keyword wins the ---
# --- prose scan, not only the payload scan above ---
#
# The two blockquote tests just above cover the review-data PAYLOAD scan,
# which already blanked blockquoted lines before this PR. strip_machine_payloads
# did not, so a blockquoted `> ### Verdict` heading still matched
# header_regex (its third alternative allows a leading `>` in
# `[ \t>*_#-]*`), moved last_idx to the quote, and a blockquoted
# `> **Ready for merge**` after it then read as content_lines[0] and matched
# clean_kw regardless of the leading `>` (`\bready\s+for\s+merge\b` does not
# care what precedes it). Reproduced against the pre-fix script (52b7ad0):
# this exact body classified clean=true verdict=ready-for-merge although its
# own (unquoted) verdict says Needs more work.
run_test "A blockquoted Ready-for-merge citation does not override Needs more work" \
"### Verdict

**Needs more work** -- one issue remains.

> Earlier this said:
> ### Verdict
> **Ready for merge**" \
"false" "needs-more-work"

# Mirror of the test above: the body's own verdict is Ready for merge, and
# what is quoted is an earlier Needs more work. Reproduced against 52b7ad0:
# this body classified clean=false verdict=needs-more-work.
run_test "A blockquoted Needs-more-work citation does not override Ready for merge" \
"### Verdict

**Ready for merge**

> Earlier this said:
> ### Verdict
> **Needs more work**" \
"true" "ready-for-merge"

# gha#845 review, finding 2: the JSON body used to be captured with a
# non-greedy `(.*?)\s*-->` regex, which cannot tell a "-->" INSIDE a JSON
# string value from the marker's own closing delimiter and truncates there.
# A NOT_CLEAN payload whose "note" field contains the three characters
# "-->" produced invalid JSON that way, fell back to the prose scan, and
# read "Ready for merge" from the surrounding text -- silently discarding
# an explicit NOT_CLEAN. json.JSONDecoder().raw_decode parses exactly one
# JSON value regardless of what its strings contain, so this now stays
# NOT_CLEAN.
run_test "NOT_CLEAN payload with a literal --> inside a JSON string still wins" \
"### Verdict

**Ready for merge.**

<!-- review-data: {\"schema_version\":\"1.1\",\"verdict\":\"NOT_CLEAN\",\"note\":\"see --> for details\"} -->" \
"false" "needs-more-work"

# gha#845 review, finding 3: a CLEAN verdict with a non-empty findings array
# is internally inconsistent and must not be trusted as a fast path -- fall
# through to the prose scan instead of inventing a NOT_CLEAN this code never
# observed.
run_test "CLEAN payload with non-empty findings falls back to the prose scan" \
"### Verdict

**Needs more work** -- see findings.

<!-- review-data: {\"schema_version\":\"1.1\",\"verdict\":\"CLEAN\",\"findings\":[{\"file\":\"foo.py\",\"note\":\"bug\"}]} -->" \
"false" "needs-more-work"

# --- gha#845 review, finding 4: the old bare (unanchored) "no action" ---
#
# "no\s+action" used to be a plain clean_kw alternative, scanned against
# EVERY content line, so it matched ordinary prose that has nothing to do
# with the verdict -- and because the scan is last-line-wins, a later such
# sentence overrode a real, earlier rejection. The fix restricts the check
# to content_lines[0] (the verdict line itself), so a later explanatory
# sentence that merely starts with the words "no action" no longer counts.
run_test "'No action has been taken' after Changes requested stays a rejection" \
"### Verdict

**Changes requested**

No action has been taken since the last round." \
"false" "changes-requested"

# Same shape for the removed "does not need (code) review" keyword: it has
# no anchor to fall back on (it was removed outright, not anchored), so
# this only ever passed because the fix stops scanning that phrase at all,
# leaving the earlier "Changes requested" line as the only match.
run_test "'does not need review' after Changes requested stays a rejection" \
"### Verdict

**Changes requested**

This does not need review from a human once that's fixed." \
"false" "changes-requested"

# --- gha#845 second review, finding 1: "no action" anchor was too loose ---
#
# The anchor only checked that the verdict line STARTED with "no action",
# which is necessary but not sufficient: this sentence also starts with
# those two words while describing unresolved work, and used to score
# clean=true. The fix requires the rest of that line to carry no
# still-open vocabulary and no rejection keyword before the anchor is
# allowed to classify; here it fires on neither "but" nor "still open", so
# the anchor backs off and nothing else in the line matches either.
run_test "'No action ... but still open issues' is not the clean exemption" \
"### Verdict

No action was taken on the flaky test, but there are still open issues to resolve here." \
"false" "unrecognized"

# The anchor still recognizes the template's actual shape, including the
# now-permitted "needed" suffix, once the guard clauses find nothing open.
run_test "'No action needed -- trivial rename.' is the clean exemption" \
"### Verdict

No action needed -- trivial rename." \
"true" "ready-for-merge"

# --- gha#845 second review, finding 2: heading and verdict on one line ---
#
# header_regex matches "Verdict" wherever it appears on the line, so a
# heading and its verdict content written on the SAME line used to survive
# into content_lines[0] with the "Verdict:" label still attached at the
# front -- which defeated the line-anchored no_action_anchor check and
# scored unrecognized. Stripping the leading heading/label prefix from
# verdict_lines[0] fixes both the ATX-heading-with-colon form and the
# bold-label form.
run_test "ATX heading and verdict on one line ('### Verdict: No action -- trivial')" \
"### Verdict: No action -- trivial" \
"true" "ready-for-merge"

run_test "Bold-label heading and verdict on one line ('**Verdict:** No action ...')" \
"## Code Review

**Verdict:** No action -- automated, trivial PR that does not need code review." \
"true" "ready-for-merge"

run_test "ATX heading and a rejection on one line ('### Verdict: Needs more work')" \
"### Verdict: Needs more work" \
"false" "needs-more-work"

# --- gha#845 second review, finding 3: tab/4-space-indented fences ---
#
# _FENCE_OPEN_RE/_FENCE_CLOSE_RE used to allow only 0-3 spaces of
# indentation before a fence marker, so a tab- or 4-space-indented ```
# fence was not tracked as a fence at all -- the review-data payload it
# enclosed was then scanned like ordinary unfenced text and trusted as the
# live verdict even though the prose verdict said "Needs more work". Both
# regexes now recognize a fence preceded by a tab or by any number of
# spaces.
run_test "A tab-indented fence around a stale CLEAN payload does not override Needs more work" \
"### Verdict

**Needs more work** -- one issue remains.

	\`\`\`
<!-- review-data: {\"schema_version\":\"1.1\",\"verdict\":\"CLEAN\"} -->
	\`\`\`" \
"false" "needs-more-work"

# A payload indented 4 spaces with NO fence markers at all is CommonMark's
# plain indented code block -- a construct the old fence tracking never
# modeled either way, since there is no ``` to look for. It is excluded
# from the payload scan directly (_INDENTED_RE), rather than through fence
# tracking.
run_test "A 4-space-indented stale CLEAN payload (no fence) does not override Needs more work" \
"### Verdict

**Needs more work** -- one issue remains.

    <!-- review-data: {\"schema_version\":\"1.1\",\"verdict\":\"CLEAN\"} -->" \
"false" "needs-more-work"

# --- gha#845 second review, finding 4: an emphasis-only first line ---
#
# content_lines[0] used to be the line the anchor check ran against,
# unconditionally. An emphasis-only line ("**" with nothing else) strips to
# empty text, so when the real verdict sentence sits on a LATER content
# line, the anchor never saw it and the review scored unrecognized. The
# check now runs on the first content line that is non-empty after
# strip_emphasis, which is content_lines[1] here.
run_test "An emphasis-only first content line does not hide the real verdict" \
"### Verdict

**

No action needed -- automated, trivial PR." \
"true" "ready-for-merge"

echo "classify-review-verdict tests: $passed passed, $failed failed."

if (( failed > 0 )); then
  exit 1
fi
exit 0
