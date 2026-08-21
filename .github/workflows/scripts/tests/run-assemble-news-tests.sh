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

# Test 3: A custom headings map replaces the built-in one, in the given order
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Infra change.\n' > news.d/infra-x.infrastructure.md
printf -- '- Doc change.\n'   > news.d/doc-y.docs.md
printf -- '- Fix Z.\n'        > news.d/fix-z.fixed.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)
NEWS

ASSEMBLE_NEWS_HEADINGS='
  fixed = Bug fixes
  infrastructure = Infrastructure
  docs = Documentation
' bash "$assemble_script" news.d NEWS.md

grep -q '^## Infrastructure$' NEWS.md || { echo "FAIL: Missing ## Infrastructure heading"; exit 1; }
grep -q '^## Documentation$' NEWS.md  || { echo "FAIL: Missing ## Documentation heading"; exit 1; }
grep -q '^## Minor improvements$' NEWS.md && { echo "FAIL: Built-in heading leaked into a custom map"; exit 1; }

order="$(grep -n '^## ' NEWS.md | cut -d: -f2- | tr '\n' '|')"
[ "$order" = "## Bug fixes|## Infrastructure|## Documentation|" ] || {
  echo "FAIL: Heading order was '$order', expected the order given in the input"; exit 1; }

echo "PASS: Test 3 - Custom headings map replaces the default, in input order"

# Test 4: A fragment outside the active map is an error, and nothing is consumed
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Add feature D.\n' > news.d/feature-d.added.md
printf -- '- Mystery change.\n' > news.d/mystery-e.nosuchcategory.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)
NEWS

if bash "$assemble_script" news.d NEWS.md 2>/dev/null; then
  echo "FAIL: Expected script to fail on an unrecognized category"
  exit 1
fi

[ -f news.d/mystery-e.nosuchcategory.md ] || { echo "FAIL: Unknown-category fragment was deleted"; exit 1; }
[ -f news.d/feature-d.added.md ] || { echo "FAIL: Valid fragment consumed despite the failure"; exit 1; }
grep -q '^## ' NEWS.md && { echo "FAIL: NEWS.md was modified despite the failure"; exit 1; }

echo "PASS: Test 4 - Unrecognized category fails before consuming anything"

# Test 5: A README (no category segment) in the fragments dir is left alone
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '# Fragments\n' > news.d/README.md
printf -- '- Add feature F.\n' > news.d/feature-f.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)
NEWS

bash "$assemble_script" news.d NEWS.md

[ -f news.d/README.md ] || { echo "FAIL: README.md was consumed as a fragment"; exit 1; }
grep -q 'Add feature F' NEWS.md || { echo "FAIL: Fragment alongside README was not collated"; exit 1; }

echo "PASS: Test 5 - A file with no category segment is neither flagged nor consumed"

# Test 6: Two categories sharing one heading collate under a single heading
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Bug one.\n' > news.d/one.fixed.md
printf -- '- Bug two.\n' > news.d/two.bug.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)
NEWS

bash "$assemble_script" news.d NEWS.md

[ "$(grep -c '^## Bug fixes$' NEWS.md)" -eq 1 ] || { echo "FAIL: Shared heading was emitted more than once"; exit 1; }
grep -q 'Bug one' NEWS.md && grep -q 'Bug two' NEWS.md || { echo "FAIL: A shared-heading fragment went missing"; exit 1; }

echo "PASS: Test 6 - Categories sharing a heading collate under one heading"

# Test 7: A malformed headings entry is rejected
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Add feature G.\n' > news.d/feature-g.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)
NEWS

if ASSEMBLE_NEWS_HEADINGS='added' bash "$assemble_script" news.d NEWS.md 2>/dev/null; then
  echo "FAIL: Expected script to fail on a headings entry with no '='"
  exit 1
fi

if ASSEMBLE_NEWS_HEADINGS='added = New features
added = Something else' bash "$assemble_script" news.d NEWS.md 2>/dev/null; then
  echo "FAIL: Expected script to fail on a duplicated category"
  exit 1
fi

[ -f news.d/feature-g.added.md ] || { echo "FAIL: Fragment consumed despite a malformed headings input"; exit 1; }

echo "PASS: Test 7 - Malformed and duplicated headings entries are rejected"

echo "=== All assemble-news.sh tests passed! ==="
