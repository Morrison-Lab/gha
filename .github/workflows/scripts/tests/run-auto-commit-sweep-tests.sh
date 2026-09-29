#!/usr/bin/env bash
# Exercises auto-commit sweep cleanup logic offline (gha#981, gha#983).
# Usage: bash .github/workflows/scripts/tests/run-auto-commit-sweep-tests.sh

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"

failures=0

cleanup_sweep() {
  find . -name '.tmp_*' -not -path '*/.git/*' 2>/dev/null | while IFS= read -r p; do
    git checkout HEAD -- "$p" 2>/dev/null || rm -rf "$p" 2>/dev/null || true
  done
  for artifact in .github/pkg.lock .github/r-depends.rds; do
    git checkout HEAD -- "$artifact" 2>/dev/null || rm -rf "$artifact" 2>/dev/null || true
  done
}

# Test 1: Untracked scratch files and setup artifacts are purged
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

(
  cd "$tmp_dir"
  git init -q
  git config user.name test
  git config user.email test@test
  echo "init" > README.md
  git add README.md
  git commit -qm "init"

  touch .tmp_find_claude.py
  mkdir -p sub
  touch sub/.tmp_scratch.sh
  mkdir -p .github
  touch .github/pkg.lock
  touch .github/r-depends.rds

  cleanup_sweep

  if [ -e .tmp_find_claude.py ] || [ -e sub/.tmp_scratch.sh ] || [ -e .github/pkg.lock ] || [ -e .github/r-depends.rds ]; then
    echo "::error::cleanup_sweep failed to purge untracked scratch/setup artifacts"
    exit 1
  fi
) || failures=$((failures + 1))
echo "OK   cleanup_sweep purges untracked scratch files and setup artifacts"

# Test 2: Tracked scratch files and setup artifacts are restored to HEAD, not deleted
(
  cd "$tmp_dir"
  touch .tmp_tracked.py
  mkdir -p .github
  echo "version 1" > .github/pkg.lock
  git add .tmp_tracked.py .github/pkg.lock
  git commit -qm "track scratch and lockfile"

  # Modify them
  echo "modified scratch" > .tmp_tracked.py
  echo "version 2" > .github/pkg.lock
  # Also make a legitimate change
  echo "legit new file" > feature.txt
  echo "modified readme" >> README.md
  # And add a new untracked scratch file
  touch .tmp_untracked.py

  cleanup_sweep

  if [ ! -f .tmp_tracked.py ] || [ ! -f .github/pkg.lock ]; then
    echo "::error::tracked scratch/lockfile was deleted instead of restored"
    exit 1
  fi

  if [ "$(cat .github/pkg.lock)" != "version 1" ]; then
    echo "::error::tracked lockfile was not restored to HEAD content"
    exit 1
  fi

  if [ -e .tmp_untracked.py ]; then
    echo "::error::untracked scratch file was not deleted"
    exit 1
  fi

  # Legitimate edits must still be dirty
  if ! git status --porcelain | grep -q "README.md"; then
    echo "::error::legitimate edit to README.md was lost"
    exit 1
  fi

  if [ ! -f feature.txt ]; then
    echo "::error::legitimate new file feature.txt was deleted"
    exit 1
  fi
) || failures=$((failures + 1))
echo "OK   cleanup_sweep restores tracked artifacts to HEAD and preserves legitimate edits"

# Test 3: Static check: claude.yml and gemini.yml contain the cleanup block at all auto-commit sites
claude_yml="$repo_root/.github/workflows/claude.yml"
gemini_yml="$repo_root/.github/workflows/gemini.yml"

claude_count=$(grep -c "find . -name '.tmp_\*'" "$claude_yml" || true)
if [ "$claude_count" -eq 2 ]; then
  echo "OK   claude.yml contains scratch cleanup in both PR and issue auto-commit steps"
else
  echo "::error::claude.yml expected 2 cleanup blocks, found $claude_count"
  failures=$((failures + 1))
fi

gemini_count=$(grep -c "find . -name '.tmp_\*'" "$gemini_yml" || true)
if [ "$gemini_count" -eq 2 ]; then
  echo "OK   gemini.yml contains scratch cleanup in both PR and issue auto-commit steps"
else
  echo "::error::gemini.yml expected 2 cleanup blocks, found $gemini_count"
  failures=$((failures + 1))
fi

if [ "$failures" -gt 0 ]; then
  echo "::error::$failures auto-commit sweep test case(s) failed"
  exit 1
fi

echo "All auto-commit sweep test cases passed."
