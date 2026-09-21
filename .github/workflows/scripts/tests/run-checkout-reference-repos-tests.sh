#!/usr/bin/env bash
# Exercises checkout-reference-repos.sh offline against throwaway git repositories.
#
# Usage: bash .github/workflows/scripts/tests/run-checkout-reference-repos-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
script="$repo_root/.github/workflows/scripts/checkout-reference-repos.sh"

failures=0

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cd "$tmp_dir"

# Create dummy upstream repo
mkdir -p "$tmp_dir/remote1.git"
(
  cd "$tmp_dir/remote1.git"
  git init --bare -b main -q 2>/dev/null || git init --bare -q
)
repo1_work="$tmp_dir/work1"
mkdir -p "$repo1_work"
(
  cd "$repo1_work"
  git init -b main -q 2>/dev/null || { git init -q && git branch -m main; }
  git config user.email "test@example.invalid"  # phi-allow
  git config user.name "test"
  echo "dummy1" > README.md
  git add README.md
  git commit -m "init" -q
  git remote add origin "$tmp_dir/remote1.git"
  git push -u origin HEAD -q
)

# Test workspace
ws="$tmp_dir/workspace"
mkdir -p "$ws"
cd "$ws"
git init -b main -q 2>/dev/null || { git init -q && git branch -m main; }
git config user.email "test@example.invalid"  # phi-allow
git config user.name "test"
echo "caller" > caller.txt
git add caller.txt
git commit -m "caller init" -q

output_file="$tmp_dir/output.txt"

# Test Case 1: Empty reference-repos input
rm -f "$output_file"
GITHUB_WORKSPACE="$ws" GITHUB_OUTPUT="$output_file" REPOS="" CURRENT_REPO="test/caller" bash "$script" > "$tmp_dir/log1.txt"

if grep -q '^dir=$' "$output_file" && grep -q '^repos=$' "$output_file"; then
  echo "OK   checkout-reference-repos.sh handles empty input gracefully"
else
  echo "::error::checkout-reference-repos.sh failed on empty input"
  failures=$((failures + 1))
fi

# Test Case 2: Self-repo skip
rm -f "$output_file"
GITHUB_WORKSPACE="$ws" GITHUB_OUTPUT="$output_file" REPOS="test/caller" CURRENT_REPO="test/caller" bash "$script" > "$tmp_dir/log2.txt"

if grep -q 'Skipping self-clone of current repository' "$tmp_dir/log2.txt" && grep -q '^repos=$' "$output_file"; then
  echo "OK   checkout-reference-repos.sh correctly skips self-repository"
else
  echo "::error::checkout-reference-repos.sh failed to skip self-repository"
  failures=$((failures + 1))
fi

# Test Case 3: Git exclude and guidance generation
rm -f "$output_file"
# Override clone URL logic by pointing url.insteadOf to our local bare repo
git config --global url."$tmp_dir/remote1.git".insteadOf "https://github.com/test/remote1.git"
trap 'git config --global --unset url."$tmp_dir/remote1.git".insteadOf || true; rm -rf "$tmp_dir"' EXIT

GITHUB_WORKSPACE="$ws" GITHUB_OUTPUT="$output_file" REPOS="test/remote1" CURRENT_REPO="test/caller" bash "$script" > "$tmp_dir/log3.txt"

if [ -f "$ws/.reference-repos/test/remote1/README.md" ]; then
  echo "OK   checkout-reference-repos.sh successfully checked out remote1"
else
  echo "::error::checkout-reference-repos.sh failed to check out remote1"
  failures=$((failures + 1))
fi

if grep -q '^/.reference-repos/' "$ws/.git/info/exclude"; then
  echo "OK   checkout-reference-repos.sh added target-dir to .git/info/exclude"
else
  echo "::error::checkout-reference-repos.sh failed to exclude target-dir in .git/info/exclude"
  failures=$((failures + 1))
fi

if grep -q 'Reference Repositories Available' "$output_file" && grep -q 'test/remote1' "$output_file"; then
  echo "OK   checkout-reference-repos.sh generated guidance output"
else
  echo "::error::checkout-reference-repos.sh failed to generate guidance output"
  failures=$((failures + 1))
fi

# Verify token does not pollute global git config
rm -rf "$ws/.reference-repos/test/remote1"
rm -f "$output_file"
GITHUB_WORKSPACE="$ws" GITHUB_OUTPUT="$output_file" REPOS="test/remote1" CURRENT_REPO="test/caller" TOKEN="dummy-secret-token-12345" bash "$script" > "$tmp_dir/log4.txt" 2>&1 || true

if git config --global --get-regexp '^url\..*dummy-secret-token' >/dev/null 2>&1; then
  echo "::error::checkout-reference-repos.sh leaked TOKEN into global git config"
  failures=$((failures + 1))
else
  echo "OK   checkout-reference-repos.sh does not leak TOKEN into global git config"
fi

# Verify git status in workspace is completely clean
cd "$ws"
if [ -z "$(git status --porcelain)" ]; then
  echo "OK   git status in caller workspace remains clean after checkout"
else
  echo "::error::git status in caller workspace is dirty after checkout"
  git status --porcelain
  failures=$((failures + 1))
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures checkout-reference-repos test case(s) failed"
  exit 1
fi

echo "All checkout-reference-repos test cases passed."
