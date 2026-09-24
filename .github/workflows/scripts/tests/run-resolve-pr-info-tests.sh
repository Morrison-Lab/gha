#!/usr/bin/env bash
# Exercises resolve-pr-info.sh offline (gha#369).
# Usage: bash .github/workflows/scripts/tests/run-resolve-pr-info-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
resolve_script="$repo_root/.github/workflows/scripts/resolve-pr-info.sh"

failures=0

# Test 1: Same-repo PR
same_repo_json='{"head": {"ref": "patch-1", "repo": {"full_name": "Morrison-Lab/gha"}}}'
output_file="$(mktemp)"
GITHUB_OUTPUT="$output_file" bash "$resolve_script" --repo "Morrison-Lab/gha" --json-data "$same_repo_json" >/dev/null

if grep -q '^pr_branch=patch-1$' "$output_file" && \
   grep -q '^pr_head_repo=Morrison-Lab/gha$' "$output_file" && \
   grep -q '^is_fork=false$' "$output_file" && \
   grep -q '^ref_arg=--ref patch-1$' "$output_file"; then
  echo "OK   resolve-pr-info.sh handles same-repo PR correctly"
else
  echo "::error::resolve-pr-info.sh failed same-repo PR test"
  cat "$output_file"
  failures=$((failures + 1))
fi
rm -f "$output_file"

# Test 2: Fork PR
fork_repo_json='{"head": {"ref": "patch-fork", "repo": {"full_name": "other-user/gha"}}}'
output_file="$(mktemp)"
GITHUB_OUTPUT="$output_file" bash "$resolve_script" --repo "Morrison-Lab/gha" --json-data "$fork_repo_json" >/dev/null

if grep -q '^pr_branch=patch-fork$' "$output_file" && \
   grep -q '^pr_head_repo=other-user/gha$' "$output_file" && \
   grep -q '^is_fork=true$' "$output_file" && \
   grep -q '^ref_arg=$' "$output_file"; then
  echo "OK   resolve-pr-info.sh handles fork PR correctly"
else
  echo "::error::resolve-pr-info.sh failed fork PR test"
  cat "$output_file"
  failures=$((failures + 1))
fi
rm -f "$output_file"

# Test 3: Empty / unresolvable JSON
empty_json='{}'
output_file="$(mktemp)"
GITHUB_OUTPUT="$output_file" bash "$resolve_script" --repo "Morrison-Lab/gha" --json-data "$empty_json" >/dev/null

if grep -q '^pr_branch=$' "$output_file" && \
   grep -q '^is_fork=false$' "$output_file" && \
   grep -q '^ref_arg=$' "$output_file" && \
   grep -q '^is_closed=false$' "$output_file"; then
  echo "OK   resolve-pr-info.sh handles empty JSON correctly"
else
  echo "::error::resolve-pr-info.sh failed empty JSON test"
  cat "$output_file"
  failures=$((failures + 1))
fi
rm -f "$output_file"

# Test 4: Closed PR
closed_json='{"head": {"ref": "patch-closed", "repo": {"full_name": "Morrison-Lab/gha"}}, "state": "closed", "merged": false}'
output_file="$(mktemp)"
GITHUB_OUTPUT="$output_file" bash "$resolve_script" --repo "Morrison-Lab/gha" --json-data "$closed_json" >/dev/null

if grep -q '^pr_branch=patch-closed$' "$output_file" && \
   grep -q '^pr_state=closed$' "$output_file" && \
   grep -q '^is_closed=true$' "$output_file"; then
  echo "OK   resolve-pr-info.sh handles closed PR correctly"
else
  echo "::error::resolve-pr-info.sh failed closed PR test"
  cat "$output_file"
  failures=$((failures + 1))
fi
rm -f "$output_file"

# Test 5: Merged PR
merged_json='{"head": {"ref": "patch-merged", "repo": {"full_name": "Morrison-Lab/gha"}}, "state": "closed", "merged": true}'
output_file="$(mktemp)"
GITHUB_OUTPUT="$output_file" bash "$resolve_script" --repo "Morrison-Lab/gha" --json-data "$merged_json" >/dev/null

if grep -q '^pr_branch=patch-merged$' "$output_file" && \
   grep -q '^pr_merged=true$' "$output_file" && \
   grep -q '^is_closed=true$' "$output_file"; then
  echo "OK   resolve-pr-info.sh handles merged PR correctly"
else
  echo "::error::resolve-pr-info.sh failed merged PR test"
  cat "$output_file"
  failures=$((failures + 1))
fi
rm -f "$output_file"

# Test 6: Uppercase state and boolean closed (GraphQL / gh pr view format)
graphql_json='{"head": {"ref": "patch-gql", "repo": {"full_name": "Morrison-Lab/gha"}}, "state": "CLOSED", "closed": true}'
output_file="$(mktemp)"
GITHUB_OUTPUT="$output_file" bash "$resolve_script" --repo "Morrison-Lab/gha" --json-data "$graphql_json" >/dev/null

if grep -q '^pr_branch=patch-gql$' "$output_file" && \
   grep -q '^is_closed=true$' "$output_file"; then
  echo "OK   resolve-pr-info.sh handles uppercase CLOSED and boolean closed field correctly"
else
  echo "::error::resolve-pr-info.sh failed uppercase CLOSED test"
  cat "$output_file"
  failures=$((failures + 1))
fi
rm -f "$output_file"

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures resolve-pr-info test case(s) failed"
  exit 1
fi
echo "All resolve-pr-info test cases passed."
