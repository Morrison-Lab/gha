#!/usr/bin/env bash
# Removes the Markdown constructs that mark text as *quoted* rather than
# *meant*, so a matcher downstream sees only what the author actually said.
#
# Usage: strip-non-invoking-markup.sh < body > stripped-body
#
# Three constructs go, and they are the three standard ways to write "this is
# a literal string, not something I am addressing to you":
#
#   * blockquote lines  -- GitHub's "Quote reply" button reproduces a whole
#     comment prefixed with `> `, so citing a request would otherwise re-issue
#     it.
#   * fenced code blocks -- a documentation example.
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
# Offline tests live in tests/run-strip-non-invoking-markup-tests.sh.
set -euo pipefail

# A code span becomes a letter token rather than a space or an empty string,
# because deleting it outright lets its neighbours close up and *create* a
# match that the raw text never contained -- "@claude `foo` review" would
# collapse to "@claude  review". The token has to be letters for that reason,
# and it must not be a word any caller's pattern accepts: `detect-review-request.sh`
# admits a closed set of function words on either side of `review`, and `code`
# is one of them, so an obvious-looking `[code]` placeholder would have made
# "@claude review `x`" match through the placeholder itself.
#
# The bias this encodes is deliberate and matches the callers': a stripped
# span that suppresses a real request costs a self-review instead of a
# dispatched one, while one that fabricates a request suppresses the agent's
# answer to a question somebody actually asked.
PLACEHOLDER='elided'

tr -d '\r' | awk -v placeholder="$PLACEHOLDER" '
# Length of the run of `ch` at the start of `s`.
function run_len(s, ch,   n) {
  n = 0
  while (substr(s, n + 1, 1) == ch) n++
  return n
}

# Replace every closed inline code span in `s` with the placeholder.
#
# CommonMark closes a span with a backtick run of exactly the opening run
# length, which is why this scans runs rather than matching /`[^`]*`/: that
# pattern matches the empty string between the two opening backticks of a
# ``...`` span, leaving the span contents behind -- exactly the false verdict
# the stripping exists to prevent. An unclosed run is literal text and stays.
function strip_spans(s,   out, i, n, run, j, closerun, found) {
  out = ""
  i = 1
  n = length(s)
  while (i <= n) {
    if (substr(s, i, 1) != "`") {
      out = out substr(s, i, 1)
      i++
      continue
    }
    run = run_len(substr(s, i), "`")
    j = i + run
    found = 0
    while (j <= n) {
      if (substr(s, j, 1) == "`") {
        closerun = run_len(substr(s, j), "`")
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
      out = out substr(s, i, run)
      i += run
    }
  }
  return out
}

BEGIN { in_fence = 0; fence_char = ""; fence_len = 0 }

{
  # Leading indentation is trimmed wholesale rather than capped at the three
  # spaces CommonMark allows before a fence. A deeper indent makes it an
  # indented code block instead, which is not an invocation either, so the
  # looser reading strips strictly more non-invoking text and never less.
  bare = $0
  sub(/^[ \t]+/, "", bare)
  lead = substr(bare, 1, 1)

  if (in_fence) {
    if (lead == fence_char && run_len(bare, fence_char) >= fence_len) {
      rest = substr(bare, run_len(bare, fence_char) + 1)
      if (rest ~ /^[ \t]*$/) in_fence = 0
    }
    next
  }

  if ((lead == "`" || lead == "~") && run_len(bare, lead) >= 3) {
    fence_char = lead
    fence_len = run_len(bare, lead)
    in_fence = 1
    next
  }

  if (lead == ">") next

  print strip_spans($0)
}
'
