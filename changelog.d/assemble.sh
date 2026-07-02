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

# keepachangelog categories, in display order, mapped to their heading text.
categories=(breaking added changed deprecated removed fixed security)
declare -A heading=(
  [breaking]=Breaking [added]=Added [changed]=Changed [deprecated]=Deprecated
  [removed]=Removed [fixed]=Fixed [security]=Security
)

block=""
consumed=()
for cat in "${categories[@]}"; do
  shopt -s nullglob
  frags=( "$here"/*."$cat".md )
  shopt -u nullglob
  [ ${#frags[@]} -gt 0 ] || continue
  block+="### ${heading[$cat]}"$'\n\n'
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
tmp="$(mktemp)"
awk -v block="$block" '
  { print }
  /^## \[Unreleased\]/ && !inserted {
    print ""
    printf "%s", block
    inserted = 1
  }
' "$changelog" > "$tmp"
mv "$tmp" "$changelog"

for f in "${consumed[@]}"; do
  rm -f "$f"
done

echo "Collated ${#consumed[@]} fragment(s) into CHANGELOG.md and removed them."
echo "Review the diff, then rename '## [Unreleased]' to the new version and commit."
