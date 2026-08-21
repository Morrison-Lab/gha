#!/usr/bin/env bash
#
# Collate changelog fragments from news.d/ (or a custom fragments dir) into
# NEWS.md for R packages, then delete the consumed fragments.
#
# Each fragment is a file named  <slug>.<category>.md  (e.g. add-feature.added.md)
# whose contents are one or more markdown list bullets.
#
# By default <category> maps to:
#   breaking                -> ## Breaking changes
#   added / feature         -> ## New features
#   fixed / bug             -> ## Bug fixes
#   changed / minor / etc   -> ## Minor improvements
#
# A consumer whose changelog uses a different taxonomy overrides the whole map
# via ASSEMBLE_NEWS_HEADINGS (or a third positional argument): newline-separated
# "category = Heading" pairs. When set, it defines the complete recognized
# category set and the heading display order; several categories may share a
# heading, which then takes the position of its first-listed category.
#
# A fragment whose category is outside the active map is an error, not a silent
# skip -- the change it documents would otherwise never reach the changelog.
set -euo pipefail

frags_dir="${1:-news.d}"
news_file="${2:-NEWS.md}"
headings_spec="${3:-${ASSEMBLE_NEWS_HEADINGS:-}}"

if [ ! -d "$frags_dir" ]; then
  echo "Fragments directory '$frags_dir' does not exist."
  exit 0
fi

# Categories in display order, and the heading each collates under. Parallel
# arrays rather than one associative array because the display order of the
# headings has to be derivable, and bash associative arrays are unordered.
categories=()
declare -A heading_for=()

parse_headings_spec() {
  local line category heading
  while IFS= read -r line; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -n "$line" ] || continue

    case "$line" in
      *=*) ;;
      *)
        echo "::error::Malformed headings entry '$line'; expected 'category = Heading'." >&2
        exit 1
        ;;
    esac

    category="${line%%=*}"
    heading="${line#*=}"
    category="${category%"${category##*[![:space:]]}"}"
    heading="${heading#"${heading%%[![:space:]]*}"}"
    heading="${heading%"${heading##*[![:space:]]}"}"

    if [ -z "$category" ] || [ -z "$heading" ]; then
      echo "::error::Malformed headings entry '$line'; expected 'category = Heading'." >&2
      exit 1
    fi

    if [ -n "${heading_for["$category"]:-}" ]; then
      echo "::error::Category '$category' is mapped more than once in the headings input." >&2
      exit 1
    fi

    categories+=( "$category" )
    heading_for["$category"]="$heading"
  done <<< "$headings_spec"

  if [ ${#categories[@]} -eq 0 ]; then
    echo "::error::The headings input contained no 'category = Heading' entries." >&2
    exit 1
  fi
}

set_default_headings() {
  categories=(breaking added feature fixed bug changed minor deprecated removed security)
  heading_for=(
    [breaking]='Breaking changes'
    [added]='New features'
    [feature]='New features'
    [fixed]='Bug fixes'
    [bug]='Bug fixes'
    [changed]='Minor improvements'
    [minor]='Minor improvements'
    [deprecated]='Minor improvements'
    [removed]='Minor improvements'
    [security]='Minor improvements'
  )
}

if [ -n "${headings_spec//[[:space:]]/}" ]; then
  parse_headings_spec
else
  set_default_headings
fi

# Headings in first-listed-category order, de-duplicated.
heading_order=()
for cat in "${categories[@]}"; do
  heading="${heading_for["$cat"]}"
  seen=false
  for known in ${heading_order[@]+"${heading_order[@]}"}; do
    [ "$known" = "$heading" ] && { seen=true; break; }
  done
  [ "$seen" = true ] || heading_order+=( "$heading" )
done

# Reject fragments whose category is outside the active map, before consuming
# anything -- a silent skip leaves the change documented nowhere.
unknown=()
shopt -s nullglob
for f in "$frags_dir"/*.*.md; do
  base="${f##*/}"
  stem="${base%.md}"
  category="${stem##*.}"
  [ -n "${heading_for["$category"]:-}" ] || unknown+=( "$f" )
done
shopt -u nullglob

if [ ${#unknown[@]} -gt 0 ]; then
  echo "::error::Fragment(s) with an unrecognized category:" >&2
  printf '  %s\n' "${unknown[@]}" >&2
  echo "Recognized categories: ${categories[*]}" >&2
  exit 1
fi

declare -A heading_blocks

consumed=()
for cat in "${categories[@]}"; do
  shopt -s nullglob
  frags=( "$frags_dir"/*."$cat".md )
  shopt -u nullglob
  [ ${#frags[@]} -gt 0 ] || continue

  heading="${heading_for["$cat"]}"
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
for heading in "${heading_order[@]}"; do
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
    echo "::error::Failed to insert fragments into $news_file -- no top-level '# ' heading was matched." >&2
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
