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
# Its sibling in strip-non-invoking-markup.sh tests all three in awk.
# Here list_bullet_candidates admits only '[-*+]' list markers, and '+' is
# never a break character, so the marker guard below rejects it -- '+ + +' is
# a list, not a break. '_' never reaches here at all, since '_' is not a list
# marker (gha#747). Fewer than three markers is a list as well ('- ' and '- -'
# alike), and a run mixing marker characters ('* - -') is a list item whose
# content happens to start with a different marker.
#
# Leading indentation is deliberately not tested. A thematic break proper
# admits at most three leading spaces, but a more deeply indented
# separator-shaped line is indented-code or nested-list content, which should
# not set the whole file's bullet style either -- so skipping it stays right,
# for a different reason.
# Decides which lines open a list item, for the bullet-style scan and, via the
# same predicate, for normalization -- one definition, so the two cannot drift.
#
# Two shapes qualify, with DIFFERENT preconditions. That difference is the
# whole reason this is awk rather than a grep pattern: the second needs the
# previous line, which a line-oriented matcher cannot see.
#
#   marker + whitespace ('- item')  -- always. A list with content may
#     legitimately interrupt a paragraph, so no precondition applies.
#
#   a BARE marker ('-' alone)       -- only at the start of the file, after a
#     blank line, or directly after another line that opens a list item.
#     Elsewhere the same text is not a list item at all: after a plain
#     paragraph line a lone '-' is a SETEXT HEADING UNDERLINE, and a lone '*'
#     or '+' is lazy paragraph continuation. Verified against CommonMark via
#     markdown-it: 'Intro\n-\n' parses to <h2> with zero list items, while
#     'Intro\n\n-\n' and '- a\n-\n' both yield list items.
#
# Accepting the bare form at all is the gha#746 fix: requiring whitespace
# after the marker made an empty list item count only when it carried a
# TRAILING SPACE, so behaviour turned on an invisible character that any
# whitespace-trimming editor removes.
#
# KNOWN GAP, erring toward the pre-gha#746 behaviour rather than toward
# corruption: a bare marker after a list item's own LAZY CONTINUATION line
# ('- a' / '  more' / '-') is a list item to CommonMark but is rejected here,
# since tracking it needs real block-level parsing. The cost is that such an
# item is not normalized; the alternative -- accepting any non-blank
# predecessor -- rewrites setext headings into bullets, which destroys
# content rather than merely missing it.
#
# No interval expression ({m,n}) appears below: mawk is Debian's and Ubuntu's
# default awk and aborts the whole process on one, turning every verdict into
# a silent failure (see CLAUDE.md's strip-non-invoking-markup note).
opens_list_item_awk='
  function is_blank(l) { return l ~ /^[[:space:]]*$/ }
  function opens_item(l, in_list_context) {
    if (l ~ /^[[:space:]]*[-*+][[:space:]]/) return 1
    if (in_list_context && l ~ /^[[:space:]]*[-*+][[:space:]]*$/) return 1
    return 0
  }
'

list_bullet_candidates() {
  awk "$opens_list_item_awk"'
    BEGIN { ctx = 1 }
    {
      opens = opens_item($0, ctx)
      if (opens) print
      ctx = (is_blank($0) || opens)
    }
  ' "$1"
}

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
    done < <(list_bullet_candidates "$news_file")
  fi

  # No pre-existing bullet to take a style from (a fresh news_file, or one
  # with only prose so far) -- default to '-' so several fragments authored
  # with different markers still collate under one consistent style.
  target_bullet_marker='-'
}

normalize_bullet_markers() {
  # Rewrites only the leading list-marker character (optionally indented),
  # never text elsewhere on the line, using the SAME predicate as the
  # candidate scan above -- one definition of "this line opens a list item",
  # so detection and rewriting cannot drift apart.
  #
  # An UNSPACED run is left alone: '---' and '***' have a second marker
  # character where the predicate requires whitespace or end-of-line, so a
  # thematic break written that way does not match, and neither does an
  # emphasis '*'.
  #
  # KNOWN GAP, pre-dating gha#746 and unchanged by it: a SPACED thematic
  # break ('- - -', '* * *') does match, and is rewritten. resolve_bullet_style
  # guards against that via is_thematic_break, but that guard is wired into
  # detection only. A fragment containing a spaced break therefore has it
  # altered. Left as-is rather than fixed here, since a changelog fragment
  # carrying a thematic break is not a shape this capability has ever seen.
  awk -v marker="$1" "$opens_list_item_awk"'
    BEGIN { ctx = 1 }
    {
      line = $0
      opens = opens_item(line, ctx)
      # marker is a single [-*+], so it is never awk sub()'"'"'s special
      # '"'"'&'"'"' or backslash, and the first such character on a qualifying
      # line is the marker itself (the leading run is whitespace only).
      if (opens) sub(/[-*+]/, marker, line)
      ctx = (is_blank($0) || opens)
      print line
    }
  '
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

# gha#810: a repeat assembly into a development block that already holds
# category sections from the previous run must merge into them, not prepend a
# second "## Bug fixes" beside the first -- markdownlint's MD024 (siblings)
# rightly rejects that, and ucdavis/bcs#862's monthly run hit it. So the
# headings are split two ways against the FIRST top-level section only (the
# development block; an older release further down may carry the same heading
# and must be left alone): a heading already present there gets its new
# bullets spliced in directly under it, ahead of the bullets it already
# holds, and only the headings absent from it are emitted as a fresh block
# under the top-level heading, as before.
# Drops trailing blank lines from stdin; the awk below supplies the one blank
# that separates spliced text from what follows it. An awk rather than the
# usual sed label loop, whose branch label reads as a typo to check-typos.
strip_trailing_blank_lines() {
  awk '{ lines[NR] = $0 } END { n = NR; while (n > 0 && lines[n] ~ /^[[:space:]]*$/) n--; for (i = 1; i <= n; i++) print lines[i] }'
}

# Fence tracking in both passes: a column-0 `# ` inside a fenced code block
# (an R comment in an example) is not a heading, and reading it as the next
# top-level heading ended the development block early and re-emitted a
# duplicate section (gha#810 review round 2). A fence closes on the same
# character, at least as long as the opener, with only whitespace after it.
fence_awk='
  function fence_step(line,    run, rest, ch, len) {
    if (match(line, /^ ? ? ?(```+|~~~+)/)) {
      run = substr(line, RSTART, RLENGTH); sub(/^ +/, "", run)
      ch = substr(run, 1, 1); len = length(run); rest = substr(line, RSTART + RLENGTH)
      if (fence == "") { fence = ch; flen = len; return 1 }
      if (ch == fence && len >= flen && rest ~ /^[ \t]*$/) { fence = ""; flen = 0; return 1 }
    }
    return fence != ""
  }
'
first_section_headings="$(awk "$fence_awk"'
  { if (fence_step($0)) next }
  /^# / { if (seen) exit; seen = 1; next }
  seen && /^## / { sub(/^## /, ""); sub(/[ \t]+$/, ""); print }
' "$news_file")"

# Every temp path from here on is removed on exit, whichever path exits; the
# trap is installed before the second and third mktemp so a failure there
# cannot leak the directory.
merge_dir="$(mktemp -d)"
# Unset paths are omitted from the argv rather than passed as "", which
# rm -f still reports and which would mask a failed mktemp (Copilot on
# gha#814). The directory goes first and the file removal is explicitly
# non-fatal: `rm -f --` with no operands exits 0, but a file removal that
# fails for any other reason (a permission-denied path) would stop an
# errexit trap before the directory, and leak it.
trap 'rm -rf -- "$merge_dir"; rm -f -- ${block_file:+"$block_file"} ${tmp:+"$tmp"} 2>/dev/null || :' EXIT
block_file="$(mktemp)"
tmp="$(mktemp)"
# The manifest is PAIRS OF LINES, heading then path, read pairwise below. A
# delimited record would need a character no heading can contain, and the map
# constrains headings only to a single line (gha#810 review round 1 measured a
# tab-bearing heading losing its fragment through a tab-split manifest). The
# file name is a counter, so two headings can never share one.
manifest="$merge_dir/manifest"
: > "$manifest"
merged_n=0
block=""
for heading in "${heading_order[@]}"; do
  [ -n "${heading_blocks["$heading"]:-}" ] || continue
  if printf '%s\n' "$first_section_headings" | grep -qFx -- "$heading"; then
    # Trailing blank lines dropped: the section's own blank line after the
    # heading follows the splice, and keeping both would leave an MD012
    # double blank at the seam (the other symptom bcs#862 reported).
    merged_file="$merge_dir/$((merged_n++))"
    printf '%s' "${heading_blocks["$heading"]}" | strip_trailing_blank_lines > "$merged_file"
    printf '%s\n%s\n' "$heading" "$merged_file" >> "$manifest"
  else
    block+="## $heading"$'\n\n'"${heading_blocks["$heading"]}"
  fi
done

# Trailing blank lines dropped here too: the awk below supplies exactly one
# blank between the block and whatever followed the top-level heading, so a
# block ending in its own blank line produced an MD012 double blank at that
# seam on every assembly (gha#810).
printf '%s' "$block" | strip_trailing_blank_lines > "$block_file"

awk -v block_file="$block_file" -v manifest="$manifest" "$fence_awk"'
  BEGIN {
    while ((getline h < manifest) > 0) {
      # awk runs END after an exit in BEGIN, so a bare exit here would be
      # overwritten by the exit-42 check; flag it and let END report it.
      if ((getline f < manifest) <= 0) { manifest_bad = 1; exit 43 }
      merge_file[h] = f
    }
    close(manifest)
  }
  /^# / && fence == "" {
    if (seen) in_first = 0
    else { seen = 1; in_first = 1 }
  }
  # Spliced text is separated from whatever the file had next by a single
  # blank of its own: a blank the file already had is printed as that
  # separator, and a content line gets a synthetic blank ahead of it. Extra
  # blanks the file already carried past that point are left as found; the
  # splice adds none. This is a state flag
  # rather than a getline of the next record on purpose -- a record read with
  # getline never reaches the rules below, so a section heading sitting
  # directly under the top-level heading skipped the merge rule and lost its
  # fragments while they were still deleted (found by the tight-layout smoke
  # test during gha#810). No apostrophes in these comments: the program is
  # single-quoted.
  need_blank { if ($0 !~ /^[[:space:]]*$/) print ""; need_blank = 0 }
  # A merged section stays ONE list: the blank the file had between the
  # heading and its old bullets is held back, and dropped when the next line
  # is a bullet (new and old bullets then sit in a tight list, as they would
  # had they been written together) or printed when it is anything else, so
  # a following heading keeps its blank.
  # When the heading was tight (no blank at all) and the next line is not a
  # bullet -- a fence, a paragraph, another heading -- the separator has to
  # be synthesized, or the new bullets glue to it (gha#810 review round 4).
  # The bullet test admits a bare marker (a lone "-" line is an empty list
  # item under a heading, Test 21), as the file-wide predicate does, and
  # refuses a spaced thematic break of one character ("- - -", "* * *"),
  # which starts like a bullet and is not one (gha#814 review); "+" is never a
  # break character. Unrolled rather than an interval expression, for mawk.
  function seam_bullet(l) {
    if (l ~ /^[ \t]*(-[ \t]*-[ \t]*-[- \t]*|\*[ \t]*\*[ \t]*\*[* \t]*)$/) return 0
    return l ~ /^[ \t]*[-*+]([ \t]|$)/
  }
  hold_blank { hold_blank = 0; if ($0 ~ /^[[:space:]]*$/) { held = 1; next } else if (!seam_bullet($0)) print "" }
  held { held = 0; if (!seam_bullet($0)) print "" }
  # The fence short-circuit sits AFTER the three seam rules above, so a
  # fence line arriving at a splice seam still drains the pending blank; in
  # front of them it skipped the drain, glued a bullet to the fence, and left
  # the flag set for an unrelated later line (gha#810 review round 3).
  { if (fence_step($0)) { print; next } }
  { print }
  /^# / && !inserted {
    if ((getline probe < block_file) > 0) {
      print ""
      print probe
      while ((getline line < block_file) > 0) print line
      need_blank = 1
    }
    close(block_file)
    inserted = 1
    next
  }
  in_first && /^## / {
    h = $0; sub(/^## /, "", h); sub(/[ \t]+$/, "", h)
    # Probe first, as the block branch does: an empty fragment must not
    # leave a stray blank at the seam.
    if (h in merge_file) {
      if ((getline probe < merge_file[h]) > 0) {
        print ""
        print probe
        while ((getline line < merge_file[h]) > 0) print line
        hold_blank = 1
      }
      close(merge_file[h])
      delete merge_file[h]
    }
  }
  END {
    if (manifest_bad) exit 43
    if (!inserted) exit 42
  }
' "$news_file" > "$tmp" || {
  status=$?
  if [ $status -eq 42 ]; then
    echo "::error::Failed to insert fragments into $news_file -- no top-level '# ' heading was matched." >&2
  elif [ $status -eq 43 ]; then
    echo "::error::Internal error: merge manifest for $news_file has an odd number of lines." >&2
  else
    echo "::error::awk error ($status) while processing $news_file." >&2
  fi
  exit 1
}

mv "$tmp" "$news_file"

for f in "${consumed[@]}"; do
  rm -f "$f"
done

echo "Collated ${#consumed[@]} news fragment(s) into $news_file and removed them."
