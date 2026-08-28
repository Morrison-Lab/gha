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

if [ "$failures" -gt 0 ]; then
  echo "::error::$failures compute-incremental-range case(s) failed" >&2
  exit 1
fi
echo "All compute-incremental-range cases passed."
