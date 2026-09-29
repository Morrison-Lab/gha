#!/usr/bin/env bash
# Offline tests for compute-incremental-range.sh (gha#709, gha#717).
#
# The load-bearing case is the SHALLOW clone: claude-code-review.yml checks
# out at fetch-depth: 1, so without the script's deepen loop the prior
# reviewed commit is unreachable and the feature is inert on every real
# round -- which is what gha#717's review round 1 measured against the
# first, inline implementation. The full-clone case alone cannot see that
# regression, so if this suite is ever trimmed, keep the shallow one.
#
# Throwaway git repos are generated in $TMPDIR per the restore-workflows
# suite's precedent; nothing is committed.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
script="$here/../compute-incremental-range.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

GIT="git -c user.email=t@e.st -c user.name=t -c init.defaultBranch=main"  # phi-allow: synthetic fixture identity

# --- origin repo with five commits ---------------------------------------
origin="$tmp/origin"
mkdir -p "$origin"
( cd "$origin"
  $GIT init -q
  for i in 1 2 3 4 5; do
    echo "content $i" > "file$i.txt"
    $GIT add "file$i.txt"
    $GIT commit -q -m "subject-c$i"
  done
)
sha_of() { ( cd "$origin" && $GIT rev-parse "$1" ); }
C3=$(sha_of HEAD~2)
C5=$(sha_of HEAD)

comments_for() {
  # $1 = SHA to embed; writes a one-comment JSON array naming it.
  local sha="$1" out="$2"
  jq -n --arg sha "$sha" '[{
    "user": {"login": "github-actions[bot]"},
    "body": ("**Claude finished review**\n### Verdict\nReady for merge\n\nReviewed commit: " + $sha)
  }]' > "$out"
}

failures=0
check() {
  local label="$1" want="$2" got="$3"
  if [ "$want" != "$got" ]; then
    echo "FAIL: $label" >&2
    printf '  want: %s\n  got:  %s\n' "$want" "$got" >&2
    failures=$((failures + 1))
  else
    echo "pass  $label"
  fi
}

run_in() {
  # $1 = worktree dir, $2 = comments file; stdout captured.
  ( cd "$1" && bash "$script" "$2" )
}

# 1. Full clone: range c3..c5 lists c4 and c5, not c3.
full="$tmp/full"
$GIT clone -q "file://$origin" "$full"
comments_for "$C3" "$tmp/comments-c3.json"
out=$(run_in "$full" "$tmp/comments-c3.json")
check "full clone: section header present" "yes" "$(grep -q 'What changed since the last review round' <<<"$out" && echo yes || echo no)"
check "full clone: lists subject-c4" "yes" "$(grep -q 'subject-c4' <<<"$out" && echo yes || echo no)"
check "full clone: lists subject-c5" "yes" "$(grep -q 'subject-c5' <<<"$out" && echo yes || echo no)"
check "full clone: does not list subject-c3" "no" "$(grep -q 'subject-c3' <<<"$out" && echo yes || echo no)"
check "full clone: diffstat names file4" "yes" "$(grep -q 'file4.txt' <<<"$out" && echo yes || echo no)"

# 2. SHALLOW clone (depth 1): the deepen loop must make the range reachable.
shallow="$tmp/shallow"
$GIT clone -q --depth 1 "file://$origin" "$shallow"
check "shallow precondition: prior unreachable before the script runs" "no" \
  "$(cd "$shallow" && git cat-file -e "$C3" 2>/dev/null && echo yes || echo no)"
out=$(DEEPEN_STEP=1 run_in "$shallow" "$tmp/comments-c3.json")
check "shallow clone: deepen loop reaches the prior and lists subject-c4" "yes" "$(grep -q 'subject-c4' <<<"$out" && echo yes || echo no)"
check "shallow clone: lists subject-c5" "yes" "$(grep -q 'subject-c5' <<<"$out" && echo yes || echo no)"

# 2b. PR-MERGE-REF topology (the PRIMARY production case): the checkout is
#     a refs/pull/<n>/merge commit on no branch, with actions/checkout's
#     narrow fetch refspec, fetched at depth 1. What this case PINS is that
#     the script works on that topology at all. What it cannot pin is the
#     explicit-SHA-vs-bare deepen distinction the script's own comment
#     records (gha#717 review round 2): a local file:// server deepens along
#     any advertised ref, so the bare form passes here while failing against
#     GitHub's server, where the failure was measured empirically. Per
#     fixtures-are-not-evidence, do not read this fixture as proof either
#     way about that server-side behavior.
( cd "$origin"
  $GIT branch feature HEAD~1 >/dev/null 2>&1 || true
  merge_tree=$($GIT rev-parse 'HEAD^{tree}')
  merge_sha=$($GIT commit-tree "$merge_tree" -p HEAD~1 -p HEAD -m "Merge pull request #1")
  $GIT update-ref refs/pull/1/merge "$merge_sha"
  $GIT config uploadpack.allowReachableSHA1InWant true
)
prmerge="$tmp/prmerge"
mkdir -p "$prmerge"
( cd "$prmerge"
  $GIT init -q
  $GIT remote add origin "file://$origin"
  # actions/checkout REPLACES the default fetch refspec with the narrow
  # merge-ref one; mirror that, or a bare deepen can reach the prior via
  # refs/heads/* here when it cannot in production.
  $GIT config remote.origin.fetch '+refs/pull/1/merge:refs/remotes/pull/1/merge'
  $GIT fetch -q --depth=1 origin
  $GIT checkout -q --detach refs/remotes/pull/1/merge
)
check "pr-merge precondition: prior unreachable before the script runs" "no" \
  "$(cd "$prmerge" && git cat-file -e "$C3" 2>/dev/null && echo yes || echo no)"
out=$(DEEPEN_STEP=1 run_in "$prmerge" "$tmp/comments-c3.json")
check "pr-merge-ref checkout: deepen reaches the prior and lists subject-c4" "yes" "$(grep -q 'subject-c4' <<<"$out" && echo yes || echo no)"
check "pr-merge-ref checkout: lists subject-c5" "yes" "$(grep -q 'subject-c5' <<<"$out" && echo yes || echo no)"

# 3. DEEPEN_MAX bounds the loop: a cap too small to reach the prior emits
#    nothing rather than looping or failing.
shallow2="$tmp/shallow2"
$GIT clone -q --depth 1 "file://$origin" "$shallow2"
out=$(DEEPEN_STEP=1 DEEPEN_MAX=1 run_in "$shallow2" "$tmp/comments-c3.json")
check "deepen cap hit: emits nothing" "" "$out"

# 4. Prior == head: emits nothing.
comments_for "$C5" "$tmp/comments-c5.json"
out=$(run_in "$full" "$tmp/comments-c5.json")
check "prior == head: emits nothing" "" "$out"

# 5. Empty comment array: emits nothing.
echo '[]' > "$tmp/comments-empty.json"
out=$(run_in "$full" "$tmp/comments-empty.json")
check "no comments: emits nothing" "" "$out"

# 6. Verdict comment with no Reviewed-commit line: emits nothing.
jq -n '[{"user": {"login": "github-actions[bot]"},
        "body": "**Claude finished review**\n### Verdict\nReady for merge"}]' \
  > "$tmp/comments-nosha.json"
out=$(run_in "$full" "$tmp/comments-nosha.json")
check "no Reviewed-commit line: emits nothing" "" "$out"

# 7. Non-bot author: excluded from the population, so nothing is emitted --
#    a human quoting a Reviewed-commit line must not steer the range.
jq -n --arg sha "$C3" '[{
  "user": {"login": "some-human"},
  "body": ("### Verdict\nReady\n\nReviewed commit: " + $sha)
}]' > "$tmp/comments-human.json"
out=$(run_in "$full" "$tmp/comments-human.json")
check "human-authored comment: emits nothing" "" "$out"

# 8. Orphaned prior (full clone, valid-shaped SHA not in history): nothing.
comments_for "0123456789abcdef0123456789abcdef01234567" "$tmp/comments-orphan.json"
out=$(run_in "$full" "$tmp/comments-orphan.json")
check "orphaned prior: emits nothing" "" "$out"

# 9. Missing comments file: nothing, exit 0.
out=$(run_in "$full" "$tmp/does-not-exist.json")
check "missing comments file: emits nothing" "" "$out"

# 10. Restated clean / "no new diff" comment skipped (gha#965).
# Comment 1 is genuine on C3; comment 2 is on C4 claiming no new diff.
# The script must skip comment 2, select C3 as prior, and list C4 and C5.
C4=$(sha_of HEAD~1)
jq -n --arg c3 "$C3" --arg c4 "$C4" '[
  {
    "user": {"login": "github-actions[bot]"},
    "body": ("### Verdict\nReady for merge\n\nReviewed commit: " + $c3)
  },
  {
    "user": {"login": "github-actions[bot]"},
    "body": ("### Verdict\nReady for merge\n\nAll changes in this PR were reviewed in the previous round. No new commits or modifications have been made since the last review.\n\nReviewed commit: " + $c4)
  }
]' > "$tmp/comments-restated.json"
out=$(run_in "$full" "$tmp/comments-restated.json")
check "restated comment skipped: lists subject-c4" "yes" "$(grep -q 'subject-c4' <<<"$out" && echo yes || echo no)"
check "restated comment skipped: lists subject-c5" "yes" "$(grep -q 'subject-c5' <<<"$out" && echo yes || echo no)"
check "restated comment skipped: mandatory requirement mentions 2 unreviewed commit(s)" "yes" "$(grep -q '2 unreviewed commit(s)' <<<"$out" && echo yes || echo no)"

# 11. Explicit head-sha passed as argument 2 bounds the range to C4.
out=$(cd "$full" && bash "$script" "$tmp/comments-c3.json" "$C4")
check "explicit head-sha: lists subject-c4" "yes" "$(grep -q 'subject-c4' <<<"$out" && echo yes || echo no)"
check "explicit head-sha: does not list subject-c5" "no" "$(grep -q 'subject-c5' <<<"$out" && echo yes || echo no)"

# 12. Count-file passed as argument 3 records the commit count.
count_file="$tmp/commit-count.txt"
( cd "$full" && bash "$script" "$tmp/comments-c3.json" "$C5" "$count_file" ) >/dev/null
count_val=$(cat "$count_file" 2>/dev/null || echo "")
check "count-file records commit count 2" "2" "$count_val"

# 13. Merge commit excluded from log and count via --no-merges (gha#965).
mergerepo="$tmp/mergerepo"
$GIT clone -q "file://$origin" "$mergerepo"
( cd "$mergerepo"
  $GIT checkout -q -b side HEAD~2
  echo "side content" > "side.txt"
  $GIT add "side.txt"
  $GIT commit -q -m "subject-side"
  $GIT checkout -q main
  $GIT merge -q --no-ff side -m "Merge branch side"
)
HEAD_MERGE=$(cd "$mergerepo" && $GIT rev-parse HEAD)
merge_count_file="$tmp/merge-count.txt"
out=$(cd "$mergerepo" && bash "$script" "$tmp/comments-c3.json" "$HEAD_MERGE" "$merge_count_file")
check "merge commit not listed in log" "no" "$(grep -q 'Merge branch side' <<<"$out" && echo yes || echo no)"
check "merge count excludes merge commit (c4, c5, side = 3)" "3" "$(cat "$merge_count_file")"

# 14. Skipped review comment with structured payload skipped (gha#965).
jq -n --arg c3 "$C3" --arg c4 "$C4" '[
  {
    "user": {"login": "github-actions[bot]"},
    "body": ("### Verdict\nReady for merge\n\nReviewed commit: " + $c3)
  },
  {
    "user": {"login": "github-actions[bot]"},
    "body": ("### Verdict\n\n**Skipped**\n\n<!-- review-data: {\"schema_version\": \"1\", \"verdict\": \"SKIPPED\", \"findings\": [], \"commit_sha\": \"" + $c4 + "\"} -->\n\nReviewed commit: " + $c4)
  }
]' > "$tmp/comments-skipped.json"
out=$(run_in "$full" "$tmp/comments-skipped.json")
check "skipped payload comment skipped: lists subject-c4" "yes" "$(grep -q 'subject-c4' <<<"$out" && echo yes || echo no)"
check "skipped payload comment skipped: lists subject-c5" "yes" "$(grep -q 'subject-c5' <<<"$out" && echo yes || echo no)"
check "skipped payload comment skipped: mandatory requirement mentions 2 unreviewed commit(s)" "yes" "$(grep -q '2 unreviewed commit(s)' <<<"$out" && echo yes || echo no)"

# 15. Comment discussing "no new diff" in code span or blockquote is NOT skipped (gha#965).
jq -n --arg c4 "$C4" '[
  {
    "user": {"login": "github-actions[bot]"},
    "body": ("### Verdict\nReady for merge\n\nReviewed all changes. The author added protection against `no new diff` claims.\n\nReviewed commit: " + $c4)
  }
]' > "$tmp/comments-codespan.json"
out=$(run_in "$full" "$tmp/comments-codespan.json")
check "codespan no-diff comment not skipped: does not list subject-c4" "no" "$(grep -q 'subject-c4' <<<"$out" && echo yes || echo no)"
check "codespan no-diff comment not skipped: lists subject-c5" "yes" "$(grep -q 'subject-c5' <<<"$out" && echo yes || echo no)"

# 16. Comment discussing 'no new diff' in single-quoted prose is NOT skipped (gha#965).
jq -n --arg c4 "$C4" '[
  {
    "user": {"login": "github-actions[bot]"},
    "body": ("### Verdict\nReady for merge\n\nThe author fixed the bug where a review declares '\''no new diff'\''.\n\nReviewed commit: " + $c4)
  }
]' > "$tmp/comments-singlequote.json"
out=$(run_in "$full" "$tmp/comments-singlequote.json")
check "single-quote no-diff comment not skipped: does not list subject-c4" "no" "$(grep -q 'subject-c4' <<<"$out" && echo yes || echo no)"
check "single-quote no-diff comment not skipped: lists subject-c5" "yes" "$(grep -q 'subject-c5' <<<"$out" && echo yes || echo no)"

# 17. Comment discussing 'a no new diff claim' in unquoted plain prose is NOT skipped (gha#965).
jq -n --arg c4 "$C4" '[
  {
    "user": {"login": "github-actions[bot]"},
    "body": ("### Verdict\nReady for merge\n\nThe author fixed the bug where a review declares a no new diff claim.\n\nReviewed commit: " + $c4)
  }
]' > "$tmp/comments-unquoted-prose.json"
out=$(run_in "$full" "$tmp/comments-unquoted-prose.json")
check "unquoted-prose no-diff comment not skipped: does not list subject-c4" "no" "$(grep -q 'subject-c4' <<<"$out" && echo yes || echo no)"
check "unquoted-prose no-diff comment not skipped: lists subject-c5" "yes" "$(grep -q 'subject-c5' <<<"$out" && echo yes || echo no)"

# 18. Comment with pre-heading no-diff claim IS skipped (gha#965).
jq -n --arg c3 "$C3" --arg c4 "$C4" '[
  {
    "user": {"login": "github-actions[bot]"},
    "body": ("### Verdict\nReady for merge\n\nReviewed commit: " + $c3)
  },
  {
    "user": {"login": "github-actions[bot]"},
    "body": ("## Code Review\n\nNo new diff exists in this PR since the last round.\n\nReviewed commit: " + $c4)
  }
]' > "$tmp/comments-preheading-no-diff.json"
out=$(run_in "$full" "$tmp/comments-preheading-no-diff.json")
check "pre-heading no-diff comment skipped: lists subject-c4" "yes" "$(grep -q 'subject-c4' <<<"$out" && echo yes || echo no)"
check "pre-heading no-diff comment skipped: lists subject-c5" "yes" "$(grep -q 'subject-c5' <<<"$out" && echo yes || echo no)"

# 19. Comment discussing qualified trigger phrases is NOT skipped (gha#965).
jq -n --arg c4 "$C4" '[
  {
    "user": {"login": "github-actions[bot]"},
    "body": ("## Code Review\n\nVerified the already reviewed in the previous round check and fixed the head has not moved bug.\n\n### Verdict\nReady for merge\n\nReviewed commit: " + $c4)
  }
]' > "$tmp/comments-qualified-phrases.json"
out=$(run_in "$full" "$tmp/comments-qualified-phrases.json")
check "qualified phrases comment not skipped: does not list subject-c4" "no" "$(grep -q 'subject-c4' <<<"$out" && echo yes || echo no)"
check "qualified phrases comment not skipped: lists subject-c5" "yes" "$(grep -q 'subject-c5' <<<"$out" && echo yes || echo no)"

# 20. Comment with unqualified no-diff claim in Verdict section IS skipped (gha#965).
jq -n --arg c3 "$C3" --arg c4 "$C4" '[
  {
    "user": {"login": "github-actions[bot]"},
    "body": ("### Verdict\nReady for merge\n\nReviewed commit: " + $c3)
  },
  {
    "user": {"login": "github-actions[bot]"},
    "body": ("### Verdict\nNo new diff exists since the last round.\n\nReviewed commit: " + $c4)
  }
]' > "$tmp/comments-verdict-no-diff.json"
out=$(run_in "$full" "$tmp/comments-verdict-no-diff.json")
check "verdict no-diff comment skipped: lists subject-c4" "yes" "$(grep -q 'subject-c4' <<<"$out" && echo yes || echo no)"
check "verdict no-diff comment skipped: lists subject-c5" "yes" "$(grep -q 'subject-c5' <<<"$out" && echo yes || echo no)"

if [ "$failures" -gt 0 ]; then
  echo "::error::$failures compute-incremental-range case(s) failed" >&2
  exit 1
fi
echo "All compute-incremental-range cases passed."
