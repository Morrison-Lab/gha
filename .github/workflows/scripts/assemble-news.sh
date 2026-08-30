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
# "category = Heading" pairs. A '#' comments out a line only when it starts the
# line, so a heading may contain one. A category may not contain a dot, being a
# single filename segment. When set, it defines the complete recognized
# category set and the heading display order; several categories may share a
# heading, which then takes the position of its first-listed category.
#
# A fragment whose category is outside the active map is an error, not a silent
# skip -- the change it documents would otherwise never reach the changelog.
#
# markdownlint's MD004 defaults to style: consistent -- the assembled file's
# FIRST bullet marker sets the required style for the whole document. Since
# fragments are spliced in at the top of news_file, a fragment authored with a
# different marker than the file's dominant one would flip that requirement
# out from under every other bullet already in the file. So every inserted
# bullet is normalized to one marker: news_file's own first bullet, an
# override via ASSEMBLE_NEWS_BULLET_STYLE (or a fourth positional argument,
# one of - * +), or '-' when news_file has no bullet yet to take a style from.
set -euo pipefail

frags_dir="${1:-news.d}"
news_file="${2:-NEWS.md}"
headings_spec="${3:-${ASSEMBLE_NEWS_HEADINGS:-}}"
bullet_style_input="${4:-${ASSEMBLE_NEWS_BULLET_STYLE:-}}"

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
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    # Only a whole-line comment is a comment. Stripping from any '#' would
    # truncate a heading that legitimately contains one ("C# interop" -> "C"),
    # silently and with the fragment still collated.
    case "$line" in ''|'#'*) continue ;; esac

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

    # A category is one segment of <slug>.<category>.md, so a dot in it is
    # ambiguous: the pre-flight scan reads the last dot-segment while the
    # collation glob matches the whole string, and a dotted category whose
    # suffix is also configured collates the same fragment under both.
    case "$category" in
      *.*)
        echo "::error::Category '$category' contains a dot; a category is a single filename segment." >&2
        exit 1
        ;;
    esac

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

# Is a bullet-style candidate line a CommonMark thematic break rather than a
# list item?
#
# The distinguishing property is NOT "nothing is left once the marker and the
# whitespace are stripped" (gha#741). A genuinely empty list item -- a line
# holding a marker and the space after it, and no content -- strips to empty
# under that test too, so it was misclassified as a break and skipped even
# though its marker is a real one that should set the file's style.
#
# A thematic break is three or more matching '-', '_' or '*' characters with
# only spaces or tabs between and after them; see
# https://spec.commonmark.org/0.31.2/#thematic-breaks.
# The caller's grep admits '+' as well, and '+' is never a break character,
# so the marker guard below rejects it -- '+ + +' is a list, not a break.
# '_' never reaches here at all, since that grep does not match it.
# Fewer than three markers is a list as well ('- ' and '- -' alike), and a
# run mixing marker characters ('* - -') is a list item whose content happens
# to start with a different marker.
#
# Leading indentation is deliberately not tested. A thematic break proper
# admits at most three leading spaces, but a more deeply indented
# separator-shaped line is indented-code or nested-list content, which should
# not set the whole file's bullet style either -- so skipping it stays right,
# for a different reason.
is_thematic_break() {
  local candidate="$1" marker="$2" bare rest
  # Bracketed literals rather than a quoted "$marker" pattern: bash honours
  # quoting inside a substitution pattern only from 4.3, and a stock macOS
  # /bin/bash is 3.2. This form raises no such question, and drops a fork.
  bare="${candidate//[[:space:]]/}"
  case "$marker" in
    -)   rest="${bare//-/}" ;;
    '*') rest="${bare//[*]/}" ;;
    *)   return 1 ;;
  esac
  [ -z "$rest" ] || return 1
  [ "${#bare}" -ge 3 ]
}

resolve_bullet_style() {
  if [ -n "$bullet_style_input" ]; then
    case "$bullet_style_input" in
      -|'*'|+) target_bullet_marker="$bullet_style_input"; return ;;
      *)
        echo "::error::Invalid bullet style '$bullet_style_input'; expected one of - * +." >&2
        exit 1
        ;;
    esac
  fi

  if [ -f "$news_file" ]; then
    local candidate marker
    # The candidate scan below accepts a BARE marker on its own line, not
    # only one followed by whitespace: CommonMark renders a lone '-' as an
    # empty list item (<ul><li></li></ul>), so requiring whitespace made an
    # empty item count only when it carried a TRAILING SPACE -- the detected
    # style then flipped on an invisible character that any whitespace-
    # trimming editor removes (gha#746). is_thematic_break still classifies
    # it correctly: a bare marker gives a length-1 'bare', which fails the
    # three-character minimum a break requires.
    while IFS= read -r candidate; do
      marker="$(printf '%s\n' "$candidate" | sed -E 's/^[[:space:]]*(.).*/\1/')"
      # A CommonMark thematic break can be a run of the SAME marker
      # character separated only by whitespace ('- - -', '* * *'), which
      # also matches "marker followed by a space" and would otherwise be
      # mistaken for the file's first real bullet -- reproduced against
      # this exact scenario in review (gha#727 PR review round 1). Skip
      # such a candidate in favor of the next match rather than accepting
      # it as the file's style.
      if is_thematic_break "$candidate" "$marker"; then
        continue
      fi
      target_bullet_marker="$marker"
      return
    done < <(grep -E '^[[:space:]]*[-*+]([[:space:]]|$)' "$news_file")
  fi

  # No pre-existing bullet to take a style from (a fresh news_file, or one
  # with only prose so far) -- default to '-' so several fragments authored
  # with different markers still collate under one consistent style.
  target_bullet_marker='-'
}

normalize_bullet_markers() {
  # Rewrites only a leading list-marker character (optionally indented),
  # never text elsewhere on the line -- an emphasis '*' or a thematic-break
  # '---' does not match, since both need a SECOND marker character where
  # this pattern requires whitespace or end-of-line.
  #
  # End-of-line is accepted for the same reason the candidate scan accepts
  # it (gha#746): a bare marker is CommonMark's empty list item, so without
  # it a fragment's empty item kept its own marker while every sibling was
  # normalized -- which is precisely the MD004 flip this function exists to
  # prevent, and it too turned on an invisible trailing space.
  sed -E "s/^([[:space:]]*)[-*+]([[:space:]]|$)/\\1${1}\\2/"
}

target_bullet_marker=''
resolve_bullet_style

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
  # An empty category segment (`<slug>..md`) matches the glob above, and an
  # empty associative-array subscript is a bash-internal fatal error rather
  # than a lookup miss -- so it has to be caught before the lookup, not by it.
  if [ -z "$category" ] || [ -z "${heading_for["$category"]:-}" ]; then
    unknown+=( "$f" )
  fi
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
    heading_blocks["$heading"]="${heading_blocks["$heading"]:-}$(normalize_bullet_markers "$target_bullet_marker" < "$f")"$'\n\n'
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
