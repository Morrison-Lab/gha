#!/usr/bin/env bash
# Exercises auto-commit sweep cleanup logic offline (gha#981, gha#983).
# Usage: bash .github/workflows/scripts/tests/run-auto-commit-sweep-tests.sh

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
purge_script="$repo_root/.github/workflows/scripts/purge-session-scratch.sh"
action_file="$repo_root/.github/actions/purge-session-scratch/action.yml"

failures=0

cleanup_sweep() {
  bash "$purge_script"
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
echo "OK   purge-session-scratch.sh purges untracked scratch files and setup artifacts"

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
echo "OK   purge-session-scratch.sh restores tracked artifacts to HEAD and preserves legitimate edits"

# Test 3: Static check: composite action exists and delegates to purge-session-scratch.sh
if [ ! -f "$action_file" ]; then
  echo "::error::missing composite action file: $action_file"
  failures=$((failures + 1))
else
  if grep -q "using:[[:space:]]*composite" "$action_file" && grep -q "purge-session-scratch.sh" "$action_file"; then
    echo "OK   purge-session-scratch composite action is declared and calls purge-session-scratch.sh"
  else
    echo "::error::purge-session-scratch action.yml does not define composite using purge-session-scratch.sh"
    failures=$((failures + 1))
  fi
fi

# Test 4: Static check: claude.yml and gemini.yml invoke purge-session-scratch composite action at all 4 auto-commit sites
claude_yml="$repo_root/.github/workflows/claude.yml"
gemini_yml="$repo_root/.github/workflows/gemini.yml"

claude_count=$(grep -c "actions/purge-session-scratch@v3" "$claude_yml" || true)
if [ "$claude_count" -eq 2 ]; then
  echo "OK   claude.yml invokes purge-session-scratch composite action in both PR and issue auto-commit steps"
else
  echo "::error::claude.yml expected 2 purge-session-scratch steps, found $claude_count"
  failures=$((failures + 1))
fi

gemini_count=$(grep -c "actions/purge-session-scratch@v3" "$gemini_yml" || true)
if [ "$gemini_count" -eq 2 ]; then
  echo "OK   gemini.yml invokes purge-session-scratch composite action in both PR and issue auto-commit steps"
else
  echo "::error::gemini.yml expected 2 purge-session-scratch steps, found $gemini_count"
  failures=$((failures + 1))
fi

if [ "$failures" -gt 0 ]; then
  echo "::error::$failures auto-commit sweep test case(s) failed"
  exit 1
fi

echo "All auto-commit sweep test cases passed."
