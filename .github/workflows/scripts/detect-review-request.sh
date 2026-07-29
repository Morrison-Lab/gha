#!/usr/bin/env bash
# Decides whether a comment/review body is an explicit "@claude review"
# request -- i.e. whether claude.yml should route it to the dedicated
# code-review workflow instead of letting the agent answer it itself.
#
# Usage: printf '%s\0' <body> [<body> ...] | detect-review-request.sh
# Reads NUL-separated bodies on stdin and prints `true` if ANY of them is a
# review request, else `false`. Exits 0 either way, so a caller running under
# `set -e` can branch on the output; exits 2 if stdin carried no bodies at
# all, which can only mean the caller is miswired.
#
# Bodies arrive on stdin rather than as arguments because argv is size-capped
# and comment bodies are attacker-influenced. Linux caps a SINGLE argument at
# MAX_ARG_STRLEN (32 pages = 131072 bytes), independent of the much larger
# aggregate ARG_MAX, and GitHub allows comment bodies of 65536 CHARACTERS --
# which in mostly-4-byte UTF-8 is 256 KiB, twice the per-argument cap. One
# ordinary emoji-heavy comment from any non-bot commenter would therefore
# fail `execve` with E2BIG, and since the caller runs under `set -euo
# pipefail` with no `continue-on-error`, that reddened the whole claude job
# over an optional late-review-dispatch nicety (gha#341 review). A pipe has
# no such limit.
#
# Why a script rather than an inline `[[ ... =~ ... ]]` in claude.yml: the
# pattern below is no longer a one-liner, it is consulted from two separate
# dispatch paths (the trigger comment and the late-comment rescue scan), and
# a silent regression in it is invisible until a real review request goes
# unanswered. Offline tests live in
# tests/run-detect-review-request-tests.sh (gha#339).
set -euo pipefail

# Only these lead-ins are accepted between `@claude` and `review`, and they
# are all function words, never content words. A wider rule -- "any few words
# may intervene" -- was considered and rejected: it matches ordinary requests
# that merely contain the word, e.g. `@claude the review workflow is broken,
# can you fix it?`. A false positive is the more expensive error here, because
# claude.yml suppresses the agent's own prose reply whenever this returns true
# (see its "Post Claude's response if no code was committed" step), so a
# misfire swallows the answer to a question the user actually asked. A false
# negative only costs a self-review instead of a dispatched one.
POLITE='please|pls|plz|kindly|(can|could|would|will)[[:space:]]+you'

# Only these words may follow `review`. This is the same closed-set idea as
# POLITE, applied to the other side of the keyword: `review` may take an
# object, but only one pointing back at the PR under discussion, never at a
# topic the requester wants examined. Constraining the lead-in alone left the
# expensive error wide open at the other end -- `@claude can you review this
# and fix the failing test?` dispatched a read-only review and suppressed the
# agent's reply to the question actually asked (gha#346).
#
# The cost is real and worth stating plainly: a pure review request whose
# object happens to be an unlisted noun phrase now self-reviews instead of
# dispatching. `@claude review the changes I just pushed` is the one that
# stings, because it carries no instruction to the agent at all. That is
# still the cheap error by the same asymmetry -- a self-review instead of a
# dispatched one, rather than an unanswered question -- but the two cases
# are pinned in the test table so widening the set stays a deliberate
# decision rather than a drift.
TAIL_WORD='this|these|those|that|it|again|now|the|my|our|latest|new|pr|prs'
TAIL_WORD="$TAIL_WORD|diff|change|changes|commit|commits|push|branch|code"
TAIL_WORD="$TAIL_WORD|please|pls|plz|kindly|thanks"
TAIL="([[:space:][:punct:]]+($TAIL_WORD))*"

# `[[:space:][:punct:]]+` (rather than the `[[:space:]]+` this replaced) is
# what admits `@claude, please review` -- the phrasing that went unanswered in
# serodynamics#277 and prompted this.
#
# The request has to end its line, which is also what keeps `review` a whole
# word: `@claude reviewer` has no line end after `review`. ERE has no `\n`
# escape and bash's `=~` has no multiline flag, so "end of line" is spelled
# out as "a literal newline, or end of string".
NEWLINE=$'\n'

BOT_NAME_INPUT="${BOT_NAME:-@claude,@gemini,@gemini-cli,@ai}"
# Format comma-separated BOT_NAME into regex alternatives
BOT_ALT="$(echo "$BOT_NAME_INPUT" | tr ',' '\n' | tr ' ' '\n' | grep -v '^$' | tr '\n' '|' | sed 's/|$//')"
BOT_PATTERN="(${BOT_ALT})"

PATTERN="${BOT_PATTERN}[[:space:][:punct:]-]+(($POLITE)[[:space:][:punct:]-]+)*(re-?)?review"
PATTERN="${PATTERN}${TAIL}[[:blank:][:punct:]]*($NEWLINE|\$)"




# Blockquotes, fenced code blocks, indented code blocks, and inline code spans
# all mark text as quoted rather than meant, so they are removed before
# matching. That work lives in a sibling script because the same constructs
# gate whether the agent runs at all -- `contains(body, '@claude')` has no
# notion of Markdown either (gha#342), and two copies of a stripper is how
# this file's own pattern came to disagree with the jq copy it replaced.
#
# Code spans are the case that prompted the split: a reply on gha#341 quoting
# the accepted phrasings as inline code dispatched a review by describing the
# feature (gha#344). Blockquote stripping predates it -- GitHub's "Quote
# reply" button reproduces a whole body prefixed with `> ` -- as does the CR
# removal the CRLF-anchored pattern above needs.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STRIP_MARKUP="$SCRIPT_DIR/strip-non-invoking-markup.sh"

normalize_body() {
  bash "$STRIP_MARKUP" <<<"$1"
}

shopt -s nocasematch

count=0
match=false
# No `break` on a match: stopping early would close the pipe under the
# writer, and `pipefail` in the caller would turn that SIGPIPE into a step
# failure -- the very outcome this stdin rewrite exists to avoid.
while IFS= read -r -d '' body; do
  count=$((count + 1))
  [ -n "$body" ] || continue
  if [[ "$(normalize_body "$body")" =~ $PATTERN ]]; then
    match=true
  fi
done

if [ "$count" -eq 0 ]; then
  # `printf '%s\n'` rather than `echo`: the usage text itself contains a
  # backslash escape, which `echo` may expand depending on the shell.
  printf '%s\n' "usage: printf '%s\\0' <body> [<body> ...] | detect-review-request.sh" >&2
  exit 2
fi

echo "$match"
