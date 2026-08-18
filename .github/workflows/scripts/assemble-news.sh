#!/usr/bin/env bash
#
# Collate changelog fragments from news.d/ (or a custom fragments dir) into
# NEWS.md for R packages, then delete the consumed fragments.
#
# Each fragment is a file named  <slug>.<category>.md  (e.g. add-feature.added.md)
# whose contents are one or more markdown list bullets. <category> maps to:
#   breaking                -> ## Breaking changes
#   added / feature         -> ## New features
#   fixed / bug             -> ## Bug fixes
#   changed / minor / etc   -> ## Minor improvements
set -euo pipefail

frags_dir="${1:-news.d}"
news_file="${2:-NEWS.md}"

if [ ! -d "$frags_dir" ]; then
  echo "Fragments directory '$frags_dir' does not exist."
  exit 0
fi

# Categories in R package NEWS display order
categories=(breaking added feature fixed bug changed minor deprecated removed security)

heading_for() {
  case "$1" in
    breaking)                                  printf 'Breaking changes' ;;
    added|feature)                             printf 'New features' ;;
    fixed|bug)                                 printf 'Bug fixes' ;;
    changed|minor|deprecated|removed|security) printf 'Minor improvements' ;;
  esac
}

declare -A heading_blocks

consumed=()
for cat in "${categories[@]}"; do
  shopt -s nullglob
  frags=( "$frags_dir"/*."$cat".md )
  shopt -u nullglob
  [ ${#frags[@]} -gt 0 ] || continue

  heading="$(heading_for "$cat")"
  for f in "${frags[@]}"; do
    heading_blocks["$heading"]="${heading_blocks["$heading"]:-}$(cat "$f")"$'\n\n'
    consumed+=( "$f" )
  done
done

if [ ${#consumed[@]} -eq 0 ]; then
  echo "No news fragments found in $frags_dir to collate."
  exit 0
fi

if [ ! -f "$news_file" ]; then
  echo "::error::$news_file does not exist; cannot insert fragments." >&2
  exit 1
fi

if ! grep -q '^# ' "$news_file"; then
  echo "::error::No top-level '# ' heading found in $news_file; cannot insert fragments." >&2
  exit 1
fi

block=""
for heading in "Breaking changes" "New features" "Bug fixes" "Minor improvements"; do
  if [ -n "${heading_blocks["$heading"]:-}" ]; then
    block+="## $heading"$'\n\n'"${heading_blocks["$heading"]}"
  fi
done

block_file="$(mktemp)"
printf '%s' "$block" > "$block_file"
tmp="$(mktemp)"

awk -v block_file="$block_file" '
  { print }
  /^# / && !inserted {
    print ""
    while ((getline line < block_file) > 0) print line
    close(block_file)
    inserted = 1
  }
  END {
    if (!inserted) exit 42
  }
' "$news_file" > "$tmp" || {
  status=$?
  rm -f "$block_file" "$tmp"
  if [ $status -eq 42 ]; then
    echo "::error::Failed to insert fragments into $news_file — no top-level '# ' heading was matched." >&2
  else
    echo "::error::awk error ($status) while processing $news_file." >&2
  fi
  exit 1
}

mv "$tmp" "$news_file"
rm -f "$block_file"

for f in "${consumed[@]}"; do
  rm -f "$f"
done

echo "Collated ${#consumed[@]} news fragment(s) into $news_file and removed them."
