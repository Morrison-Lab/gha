#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
assemble_script="$here/../assemble-news.sh"

echo "=== Running assemble-news.sh unit tests ==="

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cd "$tmp_dir"

# Test 1: Successful collation into NEWS.md
mkdir -p news.d
cat <<'FRAG' > news.d/feature-a.added.md
- Add feature A ([#123](https://github.com/foo/bar/issues/123)).
FRAG

cat <<'FRAG' > news.d/fix-b.fixed.md
- Fix bug B ([#124](https://github.com/foo/bar/issues/124)).
FRAG

cat <<'NEWS' > NEWS.md
# mypackage (development version)

# mypackage 1.0.0
- Initial release.
NEWS

bash "$assemble_script" news.d NEWS.md

grep -q '## New features' NEWS.md || { echo "FAIL: Missing ## New features heading"; exit 1; }
grep -q '## Bug fixes' NEWS.md || { echo "FAIL: Missing ## Bug fixes heading"; exit 1; }
[ ! -f news.d/feature-a.added.md ] || { echo "FAIL: Fragment file not removed"; exit 1; }

echo "PASS: Test 1 - Successful collation into NEWS.md"

# Test 2: Error when NEWS.md has no top-level heading
mkdir -p news.d
cat <<'FRAG' > news.d/feature-c.added.md
- Add feature C.
FRAG

cat <<'NEWS' > NEWS.md
Some prose without top level heading
NEWS

if bash "$assemble_script" news.d NEWS.md 2>/dev/null; then
  echo "FAIL: Expected script to fail on missing top-level heading"
  exit 1
fi

[ -f news.d/feature-c.added.md ] || { echo "FAIL: Fragment was deleted despite failure!"; exit 1; }

echo "PASS: Test 2 - Protected against data loss on missing heading"

echo "=== All assemble-news.sh tests passed! ==="
