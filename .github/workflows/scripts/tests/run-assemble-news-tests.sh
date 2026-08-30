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
# them by the marker COUNT, a break needing three or more.
#
# The fixture's ONLY bullet is that empty item, which is what makes the test
# exhibit the harm rather than merely the code path. Measured with this
# repo's own lint-markdown config: the file carries no MD004 error before
# assembly, the pre-fix answer ('-', from the no-bullet-found fallback, since
# the empty item was skipped) introduces one, and the post-fix answer ('*')
# introduces none. An earlier draft placed a later '* Existing bullet.' in
# the fixture, which made the file MD004-inconsistent before assembly and
# left the error count at 1 either way -- discriminating the code path while
# demonstrating none of the damage the test is named for.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Add feature N.\n' > news.d/feature-n.added.md

{
  printf -- '# mypackage (development version)\n\n'
  # Written as a printf argument rather than as a literal heredoc line, so
  # the significant trailing space survives an editor or a linter that trims
  # trailing whitespace.
  printf -- '* \n'
} > NEWS.md

bash "$assemble_script" news.d NEWS.md

grep -q '^\* Add feature N\.$' NEWS.md || {
  echo "FAIL: An empty list item was mistaken for a thematic break, so the file's style fell back to the default '-' instead of the item's own '*'"
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

# Tests 18-20 exist because the suite could not see three mutations of
# is_thematic_break, each measured green before they were added:
# relaxing the length gate to two, accepting a run mixing '-' and '*', and
# ignoring the marker argument to hardcode '-'. Tests 15-17 use only '-' and
# '+' candidates, so nothing exercised the '*' marker path at all.

# Test 18: a '*' thematic break is recognized as one. Pins that the break
# test reads the candidate's OWN marker rather than assuming '-': hardcoding
# '-' leaves '***' with characters left over, so the break reads as a real
# bullet and sets the style to '*' -- the MD004 flip gha#727 exists to stop.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '* Add feature P.\n' > news.d/feature-p.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)

* * *

- Existing bullet.
NEWS

bash "$assemble_script" news.d NEWS.md

grep -q '^- Add feature P\.$' NEWS.md || {
  echo "FAIL: A spaced '*' thematic break was mistaken for the file's first bullet"
  exit 1
}

echo "PASS: Test 18 - A spaced '*' thematic break is skipped, not read as a bullet"

# Test 19: two markers is a list, not a break. CommonMark requires three or
# more, so '- -' is a list item whose content is another marker. Pins the
# length gate: relaxing it to two makes this line a break and sends the
# style to the later '*'.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '* Add feature Q.\n' > news.d/feature-q.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)

- -

* Existing bullet.
NEWS

bash "$assemble_script" news.d NEWS.md

grep -q '^- Add feature Q\.$' NEWS.md || {
  echo "FAIL: A two-marker line was treated as a thematic break; CommonMark requires three or more"
  exit 1
}

echo "PASS: Test 19 - Two markers is a list, not a thematic break"

# Test 20: a run MIXING marker characters is a list. A break needs three or
# more of the SAME character, so '* - -' is a list item that merely starts
# with a different marker from the one its content uses. Pins the
# same-marker test: accepting any of '-'/'*' makes this a break.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Add feature R.\n' > news.d/feature-r.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)

* - -

- Existing bullet.
NEWS

bash "$assemble_script" news.d NEWS.md

grep -q '^\* Add feature R\.$' NEWS.md || {
  echo "FAIL: A run mixing marker characters was treated as a thematic break; a break needs three or more of the SAME character"
  exit 1
}

echo "PASS: Test 20 - A run mixing marker characters is a list, not a thematic break"

# Test 21: a BARE marker -- no trailing space -- is an empty list item and
# sets the file's style. This is Test 16's sibling and the pair is the point:
# 16 writes '* ' WITH the significant trailing space, so it passes both
# before and after gha#746, and only this spelling discriminates the fix.
#
# CommonMark renders a lone marker as an empty list item (a bare '-' gives
# <ul><li></li></ul>), but the candidate scan required whitespace after the
# marker, so this line produced no candidate at all -- is_thematic_break was
# never consulted and the style fell through to the '-' default. Measured
# against main (f7c317a) before the fix: this fixture normalized the '*'
# fragment to '-'; after, to '*'.
#
# Test 16's own comment notes that its trailing space must survive an editor
# that trims trailing whitespace. That fragility is exactly what this test
# removes: with both spellings pinned, a trim turns 16 into 21 rather than
# silently reversing what 16 checks.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '* Add feature S.\n' > news.d/feature-s.added.md

# A heredoc is safe here BECAUSE there is no trailing space to preserve --
# the absence of one is the whole point of this fixture.
cat <<'NEWS' > NEWS.md
# mypackage (development version)

*
NEWS

bash "$assemble_script" news.d NEWS.md

grep -q '^\* Add feature S\.$' NEWS.md || {
  echo "FAIL: A bare list marker produced no bullet-style candidate, so the style fell back to the default '-' instead of the item's own '*'"
  exit 1
}

echo "PASS: Test 21 - A bare list marker (no trailing space) sets the file's bullet style"

# Test 22: the normalization half of gha#746. A fragment carrying its own
# empty list item must have THAT marker rewritten too, not just its
# content-bearing siblings.
#
# normalize_bullet_markers had the same whitespace-required shape as the
# candidate scan, so a bare marker inside a fragment survived untouched while
# every sibling was rewritten -- leaving a '*' item in a '-'-styled file,
# which is precisely the MD004 flip the normalization exists to prevent.
#
# This case is NOT reachable through Test 21: that one pins which style is
# DETECTED, and this one pins which lines are REWRITTEN. Removing either
# '|$' alternative alone leaves the other test green.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '* Add feature T.\n*\n* And more.\n' > news.d/feature-t.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)

- Existing bullet.
NEWS

bash "$assemble_script" news.d NEWS.md

grep -q '^\*$' NEWS.md && {
  echo "FAIL: A fragment's bare list marker escaped normalization, leaving a '*' item in a '-'-styled file -- the MD004 flip normalization exists to prevent"
  exit 1
}

grep -q '^-$' NEWS.md || {
  echo "FAIL: The fragment's empty list item is missing entirely; it should be present and normalized to '-'"
  exit 1
}

echo "PASS: Test 22 - A fragment's bare list marker is normalized like any other bullet"

# Test 23: a bare '-' directly under a paragraph line is a SETEXT HEADING
# UNDERLINE, not an empty list item, and must not set the file's style.
#
# This is the counterweight to Tests 21 and 22. Widening the scan to accept a
# bare marker (gha#746) admitted this construct too, because at the level of a
# single line the two are identical -- only the PRECEDING line separates them.
# Verified against CommonMark via markdown-it: 'Intro\n-\n' parses to <h2>
# with zero list items, while 'Intro\n\n-\n' yields a list.
#
# The harm is the same MD004 flip the normalization exists to prevent, arrived
# at from the opposite direction: the underline was read as a '-' bullet, so a
# '*'-styled file was normalized to '-'. Caught in review of gha#746 before
# release; the first draft of that fix had this defect.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '* Add feature U.\n' > news.d/feature-u.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)

Some intro paragraph
-

* Existing bullet.
NEWS

bash "$assemble_script" news.d NEWS.md

grep -q '^\* Add feature U\.$' NEWS.md || {
  echo "FAIL: A setext heading underline was read as a bullet-style candidate; the style should have come from the '*' bullet below it"
  exit 1
}

echo "PASS: Test 23 - A setext heading underline is not a bullet-style candidate"

# Test 24: the normalization side of Test 23. A fragment carrying a setext
# heading must keep it: rewriting the underline's '-' to the file's marker
# turns an <h2> into a bullet, destroying content rather than merely
# misreading it.
#
# Test 23 cannot catch this -- that one pins which style is DETECTED from
# news_file, and this pins which fragment lines are REWRITTEN.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- 'Fragment heading\n-\n\n* Add feature V.\n' > news.d/feature-v.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)

* Existing bullet.
NEWS

bash "$assemble_script" news.d NEWS.md

grep -qx -- '-' NEWS.md || {
  echo "FAIL: A fragment's setext heading underline was rewritten to the file's bullet marker, turning a heading into a list item"
  exit 1
}

echo "PASS: Test 24 - A fragment's setext heading underline is not normalized"

# Test 25: a bare '+' after a blank line sets the style. '+' is the marker
# whose handling differs mechanically -- CommonMark builds a thematic break
# only from '-', '_' or '*', so is_thematic_break rejects '+' at its case
# default and never reaches the length check that decides the other two.
# Tests 21 and 22 both use '*', so neither exercises that path.
rm -rf news.d NEWS.md
mkdir -p news.d
printf -- '- Add feature W.\n' > news.d/feature-w.added.md

cat <<'NEWS' > NEWS.md
# mypackage (development version)

+
NEWS

bash "$assemble_script" news.d NEWS.md

grep -q '^+ Add feature W\.$' NEWS.md || {
  echo "FAIL: A bare '+' did not set the file's bullet style"
  exit 1
}

echo "PASS: Test 25 - A bare '+' marker sets the file's bullet style"

echo "=== All assemble-news.sh tests passed! ==="
