#!/usr/bin/env bash
# Exercises check-tag-drift.sh offline against throwaway git repositories.
#
# Usage: bash .github/workflows/scripts/tests/run-check-tag-drift-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
drift_script="$repo_root/.github/workflows/scripts/check-tag-drift.sh"

failures=0

# Create throwaway git repo
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cd "$tmp_dir"
git init -b main -q 2>/dev/null || { git init -q && git branch -m main; }

git config user.email "selftest@example.invalid"  # phi-allow
git config user.name "selftest"

echo "initial" > file.txt
git add file.txt
git commit -m "initial commit" -q

output_file="$tmp_dir/output.txt"
summary_file="$tmp_dir/summary.md"

# Test Case 1: No vX.Y.Z release tag
GITHUB_OUTPUT="$output_file" GITHUB_STEP_SUMMARY="$summary_file" bash "$drift_script" > "$tmp_dir/log1.txt"

if grep -q 'drift=false' "$output_file" && grep -q 'No vX.Y.Z release tag found' "$tmp_dir/log1.txt"; then
  echo "OK   check-tag-drift.sh handles no semver tag gracefully"
else
  echo "::error::check-tag-drift.sh failed on no semver tag"
  failures=$((failures + 1))
fi

# Create release tag v1.0.0 and major tag v1
git tag v1.0.0
git tag v1

# Test Case 2: Zero drift
rm -f "$output_file" "$summary_file"
GITHUB_OUTPUT="$output_file" GITHUB_STEP_SUMMARY="$summary_file" bash "$drift_script" > "$tmp_dir/log2.txt"

if grep -q 'drift=false' "$output_file" && grep -q 'drift_count=0' "$output_file"; then
  echo "OK   check-tag-drift.sh reports zero drift when tag is up to date"
else
  echo "::error::check-tag-drift.sh failed on zero drift"
  failures=$((failures + 1))
fi

# Add 2 commits
echo "commit 2" >> file.txt
git commit -am "second commit" -q
echo "commit 3" >> file.txt
git commit -am "third commit" -q

# Test Case 3: 2-commit drift (with default and HEAD argument)
rm -f "$output_file" "$summary_file"
GITHUB_OUTPUT="$output_file" GITHUB_STEP_SUMMARY="$summary_file" bash "$drift_script" "HEAD" > "$tmp_dir/log3.txt"

if grep -q 'drift=true' "$output_file" && grep -q 'drift_count=2' "$output_file" && grep -q 'v1 is 2 commit(s) behind' "$tmp_dir/log3.txt"; then
  echo "OK   check-tag-drift.sh correctly detects 2-commit drift with HEAD argument"
else
  echo "::error::check-tag-drift.sh failed to detect 2-commit drift with HEAD argument"
  failures=$((failures + 1))
fi

if grep -q '### 🏷️ Major Tag Drift Notice' "$summary_file" && grep -q '\*\*v1\*\* is \*\*2\*\* commit(s) behind' "$summary_file"; then
  echo "OK   check-tag-drift.sh correctly formatted GITHUB_STEP_SUMMARY"
else
  echo "::error::check-tag-drift.sh failed to format GITHUB_STEP_SUMMARY"
  failures=$((failures + 1))
fi

# Test Case 4: Release tag v2.0.0 present but major tag v2 missing
git tag v2.0.0
rm -f "$output_file" "$summary_file"
GITHUB_OUTPUT="$output_file" GITHUB_STEP_SUMMARY="$summary_file" bash "$drift_script" > "$tmp_dir/log4.txt"

if grep -q 'drift=false' "$output_file" && grep -q "Major tag 'v2' does not exist yet" "$tmp_dir/log4.txt"; then
  echo "OK   check-tag-drift.sh handles missing major tag gracefully"
else
  echo "::error::check-tag-drift.sh failed on missing major tag"
  failures=$((failures + 1))
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures check-tag-drift test case(s) failed"
  exit 1
fi

echo "All check-tag-drift test cases passed."
