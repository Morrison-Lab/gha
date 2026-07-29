#!/usr/bin/env bash
# Removes the Markdown constructs that mark text as *quoted* rather than
# *meant*, so a matcher downstream sees only what the author actually said.
#
# Usage: strip-non-invoking-markup.sh < body > stripped-body
#
# Four constructs go, and they are the standard ways to write "this is a
# literal string, not something I am addressing to you":
#
#   * blockquote lines   -- GitHub's "Quote reply" button reproduces a whole
#     comment prefixed with `> `, so citing a request would otherwise re-issue
#     it.
#   * fenced code blocks -- a documentation example.
#   * indented code blocks -- the same thing written without a fence.
#   * inline code spans  -- the same idea one construct down, and the one that
#     bit us: a reply on gha#341 quoting the accepted phrasings as inline code
#     dispatched a review purely by describing the feature (gha#344).
#
# CRs go too. GitHub delivers comment bodies with CRLF line endings, and the
# callers' patterns anchor on a bare newline; `tr -d '\r'` is POSIX, whereas
# the `sed 's/\r$//'` idiom it replaced is GNU-only (BSD/macOS sed reads `\r`
# as a literal `r` and strips trailing `r`s instead), and `runs-on` is a
# consumer-settable input.
#
# This tracks CommonMark closely rather than approximately, because both
# directions of error are expensive and they land on different callers: under-
# stripping dispatches a review off quoted text (gha#344), while over-stripping
# drops a genuine request in the mention gate that shares this script
# (gha#342). Where the two conflict the spec is the tie-breaker, since GitHub
# renders by it and the author's intent is whatever they saw rendered.
#
# Offline tests live in tests/run-strip-non-invoking-markup-tests.sh.
set -euo pipefail

# A code span becomes a letter token rather than a space or an empty string,
# because deleting it outright lets its neighbours close up and *create* a
# match that the raw text never contained -- "@claude `foo` review" would
# collapse to "@claude  review". The token has to be letters for that reason,
# and it must not be a word any caller's pattern accepts:
# `detect-review-request.sh` admits a closed set of function words on either
# side of `review`, and `code` is one of them, so an obvious-looking `[code]`
# placeholder would have made "@claude review `x`" match through the
# placeholder itself.
PLACEHOLDER='elided'

tr -d '\r' | awk -v placeholder="$PLACEHOLDER" '
# Width in columns of the leading whitespace of `s`, counting a tab as
# advancing to the next multiple of 4 (CommonMark 0.31.2 "Tabs").
function indent_width(s,   i, c, w) {
  w = 0
  for (i = 1; i <= length(s); i++) {
    c = substr(s, i, 1)
    if (c == " ") w += 1
    else if (c == "\t") w += 4 - (w % 4)
    else break
  }
  return w
}

# `s` with its leading whitespace removed.
function strip_indent(s) {
  sub(/^[ \t]+/, "", s)
  return s
}

# Length of the run of `ch` at the start of `s`.
function run_len(s, ch,   n) {
  n = 0
  while (substr(s, n + 1, 1) == ch) n++
  return n
}

# Replace every closed inline code span in `text` with the placeholder.
#
# This runs once over the WHOLE remaining body rather than per line, because a
# code span may contain a line break: CommonMark closes a span on a backtick
# run of matching length wherever it next appears, not at end of line. A
# per-line scan therefore left a span whose delimiters sat on different lines
# unrecognized, and leaked its contents.
#
# The scan measures runs rather than matching /`[^`]*`/ for the same reason
# the run length matters at all: that pattern matches the empty string between
# the two opening backticks of a ``...`` span, leaving the span contents
# behind. An unclosed run is literal text per the spec, and stays.
function strip_spans(text,   out, i, n, run, j, closerun, found) {
  out = ""
  i = 1
  n = length(text)
  while (i <= n) {
    if (substr(text, i, 1) != "`") {
      out = out substr(text, i, 1)
      i++
      continue
    }
    run = run_len(substr(text, i), "`")
    j = i + run
    found = 0
    while (j <= n) {
      if (substr(text, j, 1) == "`") {
        closerun = run_len(substr(text, j), "`")
        if (closerun == run) {
          found = 1
          break
        }
        j += closerun
      } else {
        j++
      }
    }
    if (found) {
      out = out placeholder
      i = j + run
    } else {
      out = out substr(text, i, run)
      i += run
    }
  }
  return out
}

BEGIN {
  in_fence = 0; fence_char = ""; fence_len = 0
  in_icode = 0
  prev_blank = 1        # start of input behaves like a blank line
  kept = ""; nkept = 0
}

{
  line = $0
  blank = (line ~ /^[ \t]*$/)
  indent = indent_width(line)
  bare = strip_indent(line)
  lead = substr(bare, 1, 1)

  # --- fenced code block ------------------------------------------------
  # CommonMark caps BOTH the opening and the closing fence at three spaces of
  # indentation. Trimming indentation wholesale before the close test let a
  # 4-space-indented delimiter -- which is fence *content* -- close the block
  # early and expose the rest as prose.
  if (in_fence) {
    if (indent <= 3 && lead == fence_char && run_len(bare, fence_char) >= fence_len &&
        substr(bare, run_len(bare, fence_char) + 1) ~ /^[ \t]*$/) {
      in_fence = 0
    }
    prev_blank = blank
    next
  }

  # --- indented code block ----------------------------------------------
  # Four columns of indentation after a blank line opens one, and it runs
  # until a non-blank line dedents to three columns or fewer. The blank-line
  # precondition is what keeps an indented *list continuation* out of this
  # branch: those follow their list item directly, so over-stripping them
  # would drop a genuine request, which is the expensive error for the
  # mention gate sharing this script.
  if (in_icode) {
    if (blank || indent >= 4) { prev_blank = blank; next }
    in_icode = 0
  } else if (prev_blank && !blank && indent >= 4) {
    in_icode = 1
    prev_blank = blank
    next
  }

  if (!blank && indent <= 3) {
    if ((lead == "`" || lead == "~") && run_len(bare, lead) >= 3) {
      fence_char = lead
      fence_len = run_len(bare, lead)
      in_fence = 1
      prev_blank = blank
      next
    }
    if (lead == ">") { prev_blank = blank; next }
  }

  # Kept lines are buffered rather than printed, so the span scan below can
  # see across line boundaries.
  kept = (nkept == 0) ? line : kept "\n" line
  nkept++
  prev_blank = blank
}

END {
  if (nkept > 0) print strip_spans(kept)
}
'
