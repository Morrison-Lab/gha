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

tr -d '\r' | ${AWK:-awk} -v placeholder="$PLACEHOLDER" '
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

# Whether `bare` is a CommonMark thematic break: three or more of a single one
# of `- * _`, with only spaces or tabs between (CommonMark 0.31.2).
# Its sibling in assemble-news.sh implements the same rule in bash.
# Written as a character count rather than a regex because the POSIX ERE that
# awk uses has no backreference, so a same-character-repeated pattern (a `\1`
# in PCRE) silently never matches.
function is_thematic_break(bare,   ch, i, c, n) {
  ch = substr(bare, 1, 1)
  if (ch != "-" && ch != "*" && ch != "_") return 0
  n = 0
  for (i = 1; i <= length(bare); i++) {
    c = substr(bare, i, 1)
    if (c == ch) n++
    else if (c != " " && c != "\t") return 0
  }
  return (n >= 3)
}

# Whether `bare` is a setext heading underline: a run of only `=` or only `-`,
# trailing spaces/tabs allowed. This is a *heading* underline only when the line
# before it is paragraph text, which the caller tracks separately -- the same
# characters are otherwise a thematic break (`- * _`, >=3), a list marker, or
# ordinary text. CommonMark makes the two underline characters symmetric, and an
# indented code block opens after either with no blank line, so the `-` case
# that `is_thematic_break` already covers for >=3 dashes needs its `=` twin here
# (plus 1-2 dash underlines, which are not thematic breaks).
function is_setext_underline(bare) {
  return bare ~ /^=+[ \t]*$/ || bare ~ /^-+[ \t]*$/
}

# Whether this line is a leaf block -- an ATX heading or a thematic break --
# after which an indented code block may begin with no blank line. `bare` is the
# line with its indentation removed, `indent` its width. These two shapes need
# no context; a setext underline also qualifies but only after paragraph text,
# so the caller handles it. A list item deliberately does NOT qualify: an
# indented line after one is a list continuation, not code, and stripping it is
# the over-stripping error the mention gate must avoid (the list-continuation
# cases added in #345 guard exactly this). Both shapes are only valid at three
# columns of indentation or fewer; deeper, they are themselves code.
function heading_or_break(bare, indent) {
  if (indent > 3) return 0
  # ATX heading: 1-6 `#` then a space/tab or end of line.
  # Avoid interval quantifier `{1,6}` for mawk 1.3.4 compatibility (gha#448).
  if (bare ~ /^#+([ \t]|$)/) {
    match(bare, /^#+/)
    if (RLENGTH <= 6) return 1
  }
  if (is_thematic_break(bare)) return 1
  return 0
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
  prev_opens_icode = 1  # start of input can open an indented code block
  prev_para = 0         # ... but is not itself paragraph text (no setext under it)
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
    prev_opens_icode = 0; prev_para = 0
    next
  }

  # --- indented code block ----------------------------------------------
  # Four columns of indentation opens one when the preceding line does not leave
  # an open paragraph or list for it to lazily continue. `prev_opens_icode`
  # carries that from the previous iteration: it is set for a blank line, an ATX
  # heading, a thematic break (`heading_or_break`), or a setext underline sitting
  # under paragraph text. It runs until a non-blank line dedents to three columns
  # or fewer. The precondition is what keeps an indented *list continuation* out
  # of this branch: those follow their list item directly, so over-stripping them
  # would drop a genuine request, which is the expensive error for the mention
  # gate sharing this script.
  if (in_icode) {
    if (blank || indent >= 4) { prev_opens_icode = 0; prev_para = 0; next }
    in_icode = 0
  } else if (prev_opens_icode && !blank && indent >= 4) {
    in_icode = 1
    prev_opens_icode = 0; prev_para = 0
    next
  }

  if (!blank && indent <= 3) {
    if ((lead == "`" || lead == "~") && run_len(bare, lead) >= 3) {
      fence_char = lead
      fence_len = run_len(bare, lead)
      in_fence = 1
      prev_opens_icode = 0; prev_para = 0
      next
    }
    if (lead == ">") { prev_opens_icode = 0; prev_para = 0; next }
  }

  # Kept lines are buffered rather than printed, so the span scan below can
  # see across line boundaries.
  kept = (nkept == 0) ? line : kept "\n" line
  nkept++
  # Decide what the NEXT line inherits. A blank line, an ATX heading, or a
  # thematic break (`hd`) opens an indented code block after it with no context;
  # a setext underline does too, but only when it is actually *consumed* as one
  # -- a `=`/`-` run (`ul`) sitting under paragraph text (`prev_para`). A ul-shaped
  # run with no paragraph above it is not consumed: CommonMark makes it an
  # ordinary new paragraph, so `prev_para` must go to 1 for the next line (a later
  # underline could underline it), which is why `prev_para` keys on `consumed`
  # rather than the raw `ul` match. Otherwise a chain of underline-shaped lines
  # (`===` / `===` / indented request) mistracks state and under-strips.
  hd = heading_or_break(bare, indent)
  ul = (indent <= 3 && is_setext_underline(bare))
  consumed = (ul && prev_para)
  prev_opens_icode = (blank || hd || consumed)
  prev_para = (!blank && !hd && !consumed)
}

END {
  if (nkept > 0) print strip_spans(kept)
}
'
