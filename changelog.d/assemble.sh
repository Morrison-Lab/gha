#!/usr/bin/env bash
#
# Collate changelog fragments from changelog.d/ into CHANGELOG.md, then delete
# the consumed fragments. Run this at release time, before cutting a vX.Y.Z tag.
#
# Each fragment is a file named  <slug>.<category>.md  (e.g. add-foo.added.md)
# whose contents are one or more keepachangelog bullets. <category> is one of:
# breaking, added, changed, deprecated, removed, fixed, security. Fragments let
# each PR record its changelog note as a NEW file, so two PRs never conflict on
# the same CHANGELOG.md lines. (GitHub's merge check does not apply the
# .gitattributes `merge=union` driver, so shared-file appends still surface as
# conflicts in the PR UI — a separate file per PR avoids that entirely.)
#
# The collated entries are inserted under `## [Unreleased]`, grouped into
# `### <Category>` subsections in keepachangelog order. Keep `## [Unreleased]`
# fragment-only (don't hand-edit it) so entries never land under a duplicate
# heading; see changelog.d/README.md.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
changelog="$here/../CHANGELOG.md"

# keepachangelog categories, in display order. A plain list + `case` mapping
# (not a bash-4 `declare -A`) keeps this runnable on stock macOS bash 3.2.
categories=(breaking added changed deprecated removed fixed security)
heading_for() {
  case "$1" in
    breaking)   printf 'Breaking' ;;
    added)      printf 'Added' ;;
    changed)    printf 'Changed' ;;
    deprecated) printf 'Deprecated' ;;
    removed)    printf 'Removed' ;;
    fixed)      printf 'Fixed' ;;
    security)   printf 'Security' ;;
  esac
}

block=""
consumed=()
for cat in "${categories[@]}"; do
  shopt -s nullglob
  frags=( "$here"/*."$cat".md )
  shopt -u nullglob
  [ ${#frags[@]} -gt 0 ] || continue
  block+="### $(heading_for "$cat")"$'\n\n'
  for f in "${frags[@]}"; do
    # $(cat) strips trailing newlines; re-add exactly one blank-line separator.
    block+="$(cat "$f")"$'\n\n'
    consumed+=( "$f" )
  done
done

if [ -z "$block" ]; then
  echo "No changelog fragments to collate."
  exit 0
fi

if ! grep -q '^## \[Unreleased\]' "$changelog"; then
  echo "::error::No '## [Unreleased]' heading in $changelog; cannot insert fragments." >&2
  exit 1
fi

# Splice the collated block in immediately after the "## [Unreleased]" line.
# The block is handed to awk via a FILE (read with getline), never `-v`: a
# `-v var=value` assignment runs C-style backslash-escape processing on the
# value, which would silently corrupt a fragment containing a literal backslash
# sequence (e.g. \`cmd\`). Only the temp-file path — never the content — goes
# through `-v`.
block_file="$(mktemp)"
printf '%s' "$block" > "$block_file"   # %s: the content is written verbatim
tmp="$(mktemp)"
awk -v block_file="$block_file" '
  { print }
  /^## \[Unreleased\]/ && !inserted {
    print ""
    while ((getline line < block_file) > 0) print line
    close(block_file)
    inserted = 1
  }
' "$changelog" > "$tmp"
mv "$tmp" "$changelog"
rm -f "$block_file"

for f in "${consumed[@]}"; do
  rm -f "$f"
done

echo "Collated ${#consumed[@]} fragment(s) into CHANGELOG.md and removed them."
echo "Review the diff, then rename '## [Unreleased]' to the new version and commit."
