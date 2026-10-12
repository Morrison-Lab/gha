#!/usr/bin/env bash
# Purges temporary scratch files and untracked setup artifacts prior to auto-commit sweeps (gha#981, gha#983).
# Usage: bash purge-session-scratch.sh [directory]

set -euo pipefail

target_dir="${1:-.}"
cd "$target_dir"

# Find .tmp_* paths without failing under pipefail if find encounters an unreadable directory.
# Uses process substitution to avoid running the loop in a subshell and safely handles null-delimited paths.
while IFS= read -r -d '' p; do
  git checkout HEAD -- "$p" 2>/dev/null || rm -rf "$p" 2>/dev/null || true
done < <(find . -name '.tmp_*' -not -path '*/.git/*' -print0 2>/dev/null || true)

for artifact in .github/pkg.lock .github/r-depends.rds; do
  git checkout HEAD -- "$artifact" 2>/dev/null || rm -rf "$artifact" 2>/dev/null || true
done
