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

# Test 8: An empty category segment reports cleanly instead of crashing bash
# (review round 1: an empty associative-array subscript is a fatal bash error,
# not a lookup miss, so it must be caught before the lookup).
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Orphan bullet.\n' > news.d/slug..md

cat <<'NEWS' > NEWS.md
# mypackage (development version)
NEWS

err="$(bash "$assemble_script" news.d NEWS.md 2>&1 1>/dev/null || true)"
case "$err" in
  *"bad array subscript"*) echo "FAIL: empty category crashed bash instead of reporting"; exit 1 ;;
  *"unrecognized category"*) : ;;
  *) echo "FAIL: empty category produced no unrecognized-category error: $err"; exit 1 ;;
esac
[ -f news.d/slug..md ] || { echo "FAIL: fragment consumed despite the failure"; exit 1; }

echo "PASS: Test 8 - An empty category segment reports rather than crashing"

# Test 9: A dotted category is rejected, since the pre-flight scan reads the
# last dot-segment while the collation glob matches the whole string -- a
# dotted category whose suffix is also configured collated the file twice.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Dotted.\n' > news.d/slug.my.fixed.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)
NEWS

if ASSEMBLE_NEWS_HEADINGS='my.fixed = Dotted
fixed = Bug fixes' bash "$assemble_script" news.d NEWS.md 2>/dev/null; then
  echo "FAIL: Expected a dotted category to be rejected"
  exit 1
fi
[ "$(grep -c '^- Dotted\.$' NEWS.md || true)" -eq 0 ] || { echo "FAIL: fragment collated despite the failure"; exit 1; }

echo "PASS: Test 9 - A dotted category is rejected before it can double-collate"

# Test 10: '#' comments only a whole line, so a heading may contain one
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Interop change.\n' > news.d/x.csharp.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)
NEWS

ASSEMBLE_NEWS_HEADINGS='  # a whole-line comment, ignored
csharp = C# interop
' bash "$assemble_script" news.d NEWS.md

grep -q '^## C# interop$' NEWS.md || {
  echo "FAIL: a '#' inside a heading was stripped: $(grep '^## ' NEWS.md)"; exit 1; }
grep -q 'whole-line comment' NEWS.md && { echo "FAIL: a comment line became a heading"; exit 1; }

echo "PASS: Test 10 - '#' comments a whole line only; a heading may contain one"

# Test 11: A fragment's bullet marker is normalized to NEWS.md's own dominant
# style, so a dash-authored fragment cannot flip an asterisk-styled file's
# markdownlint MD004 requirement (gha#727).
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Add feature H.\n' > news.d/feature-h.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)

## Existing section

* Existing bullet.
NEWS

bash "$assemble_script" news.d NEWS.md

grep -q '^\* Add feature H\.$' NEWS.md || {
  echo "FAIL: Fragment bullet marker was not normalized to the file's dominant asterisk style"
  exit 1
}
grep -q '^- Add feature H\.$' NEWS.md && {
  echo "FAIL: Fragment kept its original dash marker despite an asterisk-dominant NEWS.md"
  exit 1
}

echo "PASS: Test 11 - Fragment bullet marker normalized to the consumer file's dominant style"

# Test 12: ASSEMBLE_NEWS_BULLET_STYLE overrides the auto-detected style.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Add feature I.\n' > news.d/feature-i.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)

* Existing bullet.
NEWS

ASSEMBLE_NEWS_BULLET_STYLE='+' bash "$assemble_script" news.d NEWS.md

grep -q '^+ Add feature I\.$' NEWS.md || {
  echo "FAIL: ASSEMBLE_NEWS_BULLET_STYLE override was not applied"
  exit 1
}

echo "PASS: Test 12 - ASSEMBLE_NEWS_BULLET_STYLE overrides the auto-detected style"

# Test 13: An invalid bullet-style override is rejected, and nothing is
# consumed.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Add feature J.\n' > news.d/feature-j.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)
NEWS

if ASSEMBLE_NEWS_BULLET_STYLE='x' bash "$assemble_script" news.d NEWS.md 2>/dev/null; then
  echo "FAIL: Expected script to reject an invalid bullet-style override"
  exit 1
fi
[ -f news.d/feature-j.added.md ] || { echo "FAIL: Fragment consumed despite an invalid override"; exit 1; }

echo "PASS: Test 13 - Invalid ASSEMBLE_NEWS_BULLET_STYLE override is rejected"

# Test 14: With no pre-existing bullet in NEWS.md to take a style from,
# fragments authored with different original markers still collate under one
# consistent marker rather than each keeping its own.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '* Add feature K.\n' > news.d/feature-k.added.md
printf -- '+ Fix L.\n'         > news.d/fix-l.fixed.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)
NEWS

bash "$assemble_script" news.d NEWS.md

marker_k="$(grep 'Add feature K' NEWS.md | cut -c1)"
marker_l="$(grep 'Fix L' NEWS.md | cut -c1)"
[ "$marker_k" = "$marker_l" ] || {
  echo "FAIL: Fragments with different original markers were not normalized to one style ('$marker_k' vs '$marker_l')"
  exit 1
}
# Pin the actual fallback value too -- a marker deleted outright (substituted
# with an empty target) would leave both fragments equally markerless and
# pass the equality check above vacuously.
[ "$marker_k" = "-" ] || {
  echo "FAIL: Expected the documented '-' fallback marker, got '$marker_k'"
  exit 1
}

echo "PASS: Test 14 - Fragments with differing original markers collate under one marker on a fresh NEWS.md"

# Test 15: A CommonMark spaced thematic break ('- - -') ahead of the file's
# real first bullet is not mistaken for that bullet -- it also matches
# "marker followed by a space", so the scan must recognize it as a break and
# keep going to the real bullet below it (review round 1 on gha#727's PR:
# this false-detected '-' from the break, when the file's actual dominant
# marker is '*', reproduced the exact MD004-flip bug this script exists to
# prevent).
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Add feature M.\n' > news.d/feature-m.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)

- - -

* Existing bullet.
NEWS

bash "$assemble_script" news.d NEWS.md

grep -q '^\* Add feature M\.$' NEWS.md || {
  echo "FAIL: A spaced thematic break was mistaken for the file's first bullet"
  exit 1
}

echo "PASS: Test 15 - A spaced thematic break ahead of the real first bullet is skipped"

# Test 16: An empty list item ('- ' -- a marker, a space, and no content) is
# a real bullet whose marker sets the file's style, not a thematic break.
# Both strip to empty once the marker and whitespace are removed, which is
# why the earlier heuristic conflated them (gha#741); CommonMark separates
# them by the marker COUNT, a break needing three or more. markdownlint's
# MD004 counts the empty item as the file's first bullet, so resolving to
# '*' here -- the pre-fix answer -- would flip the style out from under it.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '* Add feature N.\n' > news.d/feature-n.added.md

{
  printf -- '# mypackage (development version)\n\n'
  # Written with printf rather than inside the heredoc so the significant
  # trailing space survives an editor or a linter that trims one.
  printf -- '- \n\n'
  printf -- '* Existing bullet.\n'
} > NEWS.md

bash "$assemble_script" news.d NEWS.md

grep -q '^- Add feature N\.$' NEWS.md || {
  echo "FAIL: An empty list item was mistaken for a thematic break, so the file's style resolved to the later '*' instead of its own '-'"
  exit 1
}

echo "PASS: Test 16 - An empty list item sets the file's bullet style rather than being skipped as a break"

# Test 17: '+ + +' is a list, not a thematic break. CommonMark builds a
# thematic break only from '-', '_' or '*', so a spaced run of '+' is a
# nested list whose outermost marker is a real one -- and stripping to empty
# cannot tell the two apart, which is the other half of gha#741.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '* Add feature O.\n' > news.d/feature-o.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)

+ + +

* Existing bullet.
NEWS

bash "$assemble_script" news.d NEWS.md

grep -q '^+ Add feature O\.$' NEWS.md || {
  echo "FAIL: A spaced run of '+' was treated as a thematic break; '+' is never a thematic break marker in CommonMark"
  exit 1
}

echo "PASS: Test 17 - A spaced run of '+' is a list, not a thematic break"

echo "=== All assemble-news.sh tests passed! ==="
