#!/usr/bin/env bash
# Offline tests for restore-default-branch-workflows.sh (gha#598).
#
# Built against throwaway git repos in $TMPDIR --- nothing committed in
# this repo, because a fixture workflow under tests/ would be swept into
# other selftest jobs.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
restore="$script_dir/../restore-default-branch-workflows.sh"

failures=0
checked=0

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

init_repo() {
  local dir="$1"
  mkdir -p "$dir"
  git -C "$dir" init -q -b main
  git -C "$dir" config user.email "test@example.com"
  git -C "$dir" config user.name "test"
  mkdir -p "$dir/.github/workflows/scripts"
  printf 'name: trusted\n' > "$dir/.github/workflows/review.yml"
  printf 'echo trusted\n' > "$dir/.github/workflows/scripts/helper.sh"
  git -C "$dir" add -A
  git -C "$dir" commit -q -m "main workflows"
}

pass() {
  checked=$((checked + 1))
  echo "OK   $1"
}

fail() {
  checked=$((checked + 1))
  failures=$((failures + 1))
  echo "FAIL: $1"
}

# --- restore replaces a modified workflow and drops a PR-only file
repo="$tmpdir/extra"
init_repo "$repo"
git -C "$repo" checkout -q -b feature
printf 'name: untrusted\n' > "$repo/.github/workflows/review.yml"
printf 'name: pr-only\n' > "$repo/.github/workflows/pr-only.yml"
printf 'echo untrusted\n' > "$repo/.github/workflows/scripts/helper.sh"
git -C "$repo" add -A
git -C "$repo" commit -q -m "pr workflows"

(
  cd "$repo"
  DEFAULT_BRANCH=main DEFAULT_REF=main bash "$restore"
)

if grep -q 'name: trusted' "$repo/.github/workflows/review.yml" \
  && [ ! -f "$repo/.github/workflows/pr-only.yml" ] \
  && grep -q 'echo trusted' "$repo/.github/workflows/scripts/helper.sh"; then
  pass "restore overwrites modified files and deletes PR-only workflows"
else
  fail "restore did not replace the PR workflow tree"
  echo "  review.yml=$(cat "$repo/.github/workflows/review.yml" 2>/dev/null || echo missing)"
  echo "  pr-only exists=$([ -f "$repo/.github/workflows/pr-only.yml" ] && echo yes || echo no)"
fi

# --- missing DEFAULT_BRANCH fails closed
set +e
err_out="$(cd "$repo" && bash "$restore" 2>&1)"
err_code=$?
set -e
if [ "$err_code" -ne 0 ] && [[ "$err_out" == *"DEFAULT_BRANCH is required"* ]]; then
  pass "missing DEFAULT_BRANCH fails closed"
else
  fail "missing DEFAULT_BRANCH"
  echo "  exit $err_code, $err_out"
fi

# --- missing workflows tree on the ref fails rather than leaving the PR copy
repo2="$tmpdir/nowf"
mkdir -p "$repo2"
git -C "$repo2" init -q -b main
git -C "$repo2" config user.email "test@example.com"
git -C "$repo2" config user.name "test"
printf 'readme\n' > "$repo2/README.md"
git -C "$repo2" add -A
git -C "$repo2" commit -q -m "no workflows"
git -C "$repo2" checkout -q -b feature
mkdir -p "$repo2/.github/workflows"
printf 'name: untrusted\n' > "$repo2/.github/workflows/review.yml"
git -C "$repo2" add -A
git -C "$repo2" commit -q -m "pr added workflows"

set +e
err_out="$(cd "$repo2" && DEFAULT_BRANCH=main DEFAULT_REF=main bash "$restore" 2>&1)"
err_code=$?
set -e
if [ "$err_code" -ne 0 ] && [ -f "$repo2/.github/workflows/review.yml" ]; then
  pass "missing default-branch workflows tree fails and leaves the tree"
else
  fail "missing default-branch workflows tree"
  echo "  exit $err_code, $err_out"
  echo "  review.yml exists=$([ -f "$repo2/.github/workflows/review.yml" ] && echo yes || echo no)"
fi

# --- mutation: deleting the rm -rf would leave pr-only.yml. Confirm the
#     extra-file assertion above is reachable by running a checkout-only
#     restore in a sibling clone and checking the file remains.
repo3="$tmpdir/mutation"
init_repo "$repo3"
git -C "$repo3" checkout -q -b feature
printf 'name: pr-only\n' > "$repo3/.github/workflows/pr-only.yml"
git -C "$repo3" add -A
git -C "$repo3" commit -q -m "pr-only workflow"
git -C "$repo3" checkout -q main -- .github/workflows
if [ -f "$repo3/.github/workflows/pr-only.yml" ]; then
  pass "pathspec checkout alone does not delete a PR-only workflow (rm -rf is load-bearing)"
else
  fail "pathspec checkout unexpectedly deleted pr-only.yml; the extra-file test is vacuous"
fi

if [ "$failures" -gt 0 ]; then
  echo "::error::$failures/$checked restore-default-branch-workflows test(s) failed"
  exit 1
fi
echo "All $checked restore-default-branch-workflows cases passed."
