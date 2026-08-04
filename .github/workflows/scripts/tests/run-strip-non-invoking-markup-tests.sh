#!/usr/bin/env bash
# Exercises strip-non-invoking-markup.sh offline, mirroring
# run-detect-review-request-tests.sh's pattern. Wired into _selftest.yml's
# `review-fail-check` job (gha#344).
#
# Stripping is where a matcher's false verdicts come from, in both directions,
# so the table below pins both: text that must survive (a real request) and
# text that must not (the same request quoted). A pattern here has to remove
# its construct and nothing adjacent to it.
#
# Usage: bash .github/workflows/scripts/tests/run-strip-non-invoking-markup-tests.sh
#
# The fixtures below are single-quoted on purpose: backticks and `$` in them
# are the Markdown under test, not shell syntax, so the whole point is that
# they do not expand.
# shellcheck disable=SC2016
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
strip_script="$repo_root/.github/workflows/scripts/strip-non-invoking-markup.sh"

failures=0
checked=0

# check <name> <input> <expected-output>
check() {
  local name="$1" input="$2" want="$3" got
  checked=$((checked + 1))
  got="$(printf '%s' "$input" | bash "$strip_script")"
  if [[ "$got" == "$want" ]]; then
    echo "OK   $name"
  else
    echo "::error::$name: expected ${want@Q} but got ${got@Q}"
    failures=$((failures + 1))
  fi
}

# Ordinary prose is returned unchanged -- the stripper must not be a filter
# that quietly eats real requests.
check "plain text survives" \
  '@claude review' \
  '@claude review'

# The gha#344 case: a mention inside a code span is quoted example text.
check "single-backtick span becomes a placeholder" \
  'the accepted phrasings are `@claude review` and `@claude, review`' \
  'the accepted phrasings are elided and elided'

# A `[^`]*` pattern matches the empty string between the two opening
# backticks of a double-backtick span, so the span contents leak through. The
# run-length scanner is what stops that.
check "double-backtick span is closed by an equal run" \
  'quoting ``@claude review`` inline' \
  'quoting elided inline'

# A span containing a backtick is exactly why CommonMark allows longer runs.
check "longer run may contain a shorter one" \
  'write ``a ` b`` here' \
  'write elided here'

# An unmatched run is literal text in CommonMark, so it must not swallow the
# rest of the line.
check "unclosed run is left alone" \
  'a ` b @claude review' \
  'a ` b @claude review'

check "two spans on one line" \
  '`a` and `b`' \
  'elided and elided'

# The placeholder is letters, not a space: deleting the span outright would
# let the neighbours close up into a request the author never wrote.
check "span between mention and keyword does not close up" \
  '@claude `foo` review' \
  '@claude elided review'

# Fenced blocks go entirely, both fence characters, and a longer closing run
# is still a close.
check "backtick fence is dropped" \
  $'before\n```\n@claude review\n```\nafter' \
  $'before\nafter'

check "tilde fence is dropped" \
  $'before\n~~~\n@claude review\n~~~\nafter' \
  $'before\nafter'

check "fence with an info string is dropped" \
  $'before\n```yaml\n@claude review\n```\nafter' \
  $'before\nafter'

# A fence closes only on its own character at its own length or longer, so a
# shorter run inside the block is content, not a terminator.
check "shorter run inside a fence does not close it" \
  $'````\n```\n@claude review\n````\nafter' \
  $'after'

check "tilde does not close a backtick fence" \
  $'```\n~~~\n@claude review\n```\nafter' \
  $'after'

# An unterminated fence swallows the rest of the body. That is the
# conservative direction: the alternative is treating a half-written code
# block as prose.
check "unterminated fence drops the remainder" \
  $'text\n```\n@claude review' \
  'text'

check "blockquote lines are dropped" \
  $'> @claude review\n\n@claude review' \
  $'\n@claude review'

check "indented blockquote is dropped" \
  '   > @claude review' \
  ''

# Line deletion cannot merge two lines into one, so a mention and a keyword
# separated by a dropped block stay on separate lines.
check "dropping a block does not join its neighbours" \
  $'@claude\n```\nx\n```\nreview' \
  $'@claude\nreview'

# A span may contain a line break: CommonMark closes on the next run of
# matching length wherever it appears, not at end of line. A per-line scan
# left these unrecognized and leaked the contents.
check "code span spanning two lines" \
  $'Trigger phrase: `foo\n@claude review\nbar`' \
  'Trigger phrase: elided'

check "code span spanning three lines" \
  $'a ``x\ny\nz`` b' \
  'a elided b'

# CommonMark caps a closing fence at three spaces of indentation, so a
# 4-space-indented delimiter is content and must not terminate the block.
check "deeply indented delimiter does not close a fence" \
  $'```\n    ```\n@claude review\n```\nafter' \
  'after'

check "closing fence may be indented up to three spaces" \
  $'```\nx\n   ```\nafter' \
  'after'

# Four columns after a blank line is an indented code block -- the same
# "quoted, not meant" construct written without a fence.
check "indented code block is dropped" \
  $'The accepted phrasing is:\n\n    @claude review' \
  'The accepted phrasing is:'

check "indented code block runs until it dedents" \
  $'intro:\n\n    line one\n    line two\n\nafter' \
  $'intro:\n\nafter'

# A tab indents to the next multiple of four, so one tab opens a block.
check "tab-indented code block is dropped" \
  $'intro:\n\n\t@claude review' \
  'intro:'

# The blank-line precondition is what keeps list continuations out of the
# branch above. Over-stripping here would drop a genuine request, which is the
# expensive error for the mention gate that shares this script.
check "list continuation is not an indented code block" \
  $'- a point\n      @claude review' \
  $'- a point\n      @claude review'

check "indentation without a preceding blank line is not code" \
  $'some prose\n    @claude review' \
  $'some prose\n    @claude review'

# An indented code block also opens after a thematic break or an ATX heading
# with no blank line: neither leaves an open paragraph for the indented line to
# lazily continue (CommonMark 0.31.2, "Indented code blocks"). A request quoted
# this way must still be stripped (gha#356).
check "indented code block opens after a thematic break" \
  $'---\n    @claude review' \
  '---'

check "indented code block opens after an ATX heading" \
  $'## Accepted phrasing\n    @claude review' \
  '## Accepted phrasing'

check "indented code block opens after a spaced thematic break" \
  $'* * *\n    @claude review' \
  '* * *'

# A list item is NOT such a predecessor: an indented line after it is a list
# continuation, not code, so it must survive -- and a lone-dash item must not
# be mistaken for a thematic break, which would over-strip a genuine request.
check "indented line after a list item is not code" \
  $'- a point\n    @claude review' \
  $'- a point\n    @claude review'

check "CRLF endings are normalized" \
  $'@claude review\r\nthanks\r' \
  $'@claude review\nthanks'

check "empty input stays empty" '' ''

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of $checked strip-non-invoking-markup case(s) did not behave as expected"
  exit 1
fi
echo "All $checked strip-non-invoking-markup cases behaved as expected."
