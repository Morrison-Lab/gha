#!/usr/bin/env bash
# Exercises resolve-major-tag.sh offline against throwaway git repositories.
#
# Usage: bash .github/workflows/scripts/tests/run-resolve-major-tag-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
resolve_script="$repo_root/.github/workflows/scripts/resolve-major-tag.sh"

failures=0

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cd "$tmp_dir"
git init -q
git config user.email "selftest@example.invalid"  # phi-allow
git config user.name "selftest"

# Case 1: No tags
source "$resolve_script"
resolve_major_tag

if [[ -z "$LATEST" && -z "$MAJOR" ]]; then
  echo "OK   resolve-major-tag.sh handles repo with no tags"
else
  echo "::error::resolve-major-tag.sh failed on repo with no tags (got LATEST=$LATEST MAJOR=$MAJOR)"
  failures=$((failures + 1))
fi

# Case 2: Semver release tags
echo "init" > file.txt
git add file.txt
git commit -m "init" -q
git tag v1.0.0
git tag v1.1.0
git tag v2.0.0-rc1 # pre-release tag should be ignored

resolve_major_tag

if [[ "$LATEST" == "v1.1.0" && "$MAJOR" == "v1" ]]; then
  echo "OK   resolve-major-tag.sh correctly identifies latest release tag and major tag"
else
  echo "::error::resolve-major-tag.sh failed semver tag identification (got LATEST=$LATEST MAJOR=$MAJOR)"
  failures=$((failures + 1))
fi

# Add v2.0.0 stable tag
git tag v2.0.0
resolve_major_tag

if [[ "$LATEST" == "v2.0.0" && "$MAJOR" == "v2" ]]; then
  echo "OK   resolve-major-tag.sh correctly updates to v2.0.0"
else
  echo "::error::resolve-major-tag.sh failed on v2.0.0 tag (got LATEST=$LATEST MAJOR=$MAJOR)"
  failures=$((failures + 1))
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures resolve-major-tag test case(s) failed"
  exit 1
fi

echo "All resolve-major-tag test cases passed."
