#!/usr/bin/env bash
# Decides whether a comment/review/issue body carries a genuine `@claude`
# mention -- one addressed to the bot, rather than one merely quoted while
# writing *about* it.
#
# Usage: printf '%s\0' <body> [<body> ...] | detect-bot-mention.sh
# Reads NUL-separated bodies on stdin and prints `true` if ANY of them still
# mentions the bot once non-invoking markup is stripped, else `false`. Exits 0
# either way; exits 2 if stdin carried no bodies at all, which can only mean
# the caller is miswired.
#
# The workflows' own `if:` expressions test the raw body with `contains()`,
# which has no notion of Markdown, so a mention inside a code span, a fenced
# block, or a blockquote invokes the agent. That is not merely wasteful: the
# spawned run re-dispatches a review, and the per-PR `cancel-in-progress`
# concurrency group makes that cancel whichever review was already in flight.
# A comment *explaining* the concurrency race therefore reproduced it
# (gha#342). An `if:` expression cannot strip markup, so the raw `contains()`
# stays as a cheap pre-filter and this script makes the real decision inside
# the job.
#
# THE BIAS HERE IS THE OPPOSITE OF detect-review-request.sh's, and the two
# scripts must not be "harmonized" on this point. There, a false positive
# suppresses the agent's reply to a real question, so the matcher is
# deliberately narrow. Here, a false negative means a genuine request is
# silently ignored -- the worst outcome this workflow has -- while a false
# positive only spends a run. So this answers `true` whenever ANY mention
# survives stripping, and only reports `false` when EVERY occurrence sat
# inside markup. When in doubt, run.
#
# Matching is case-insensitive and plain-substring, mirroring the `contains()`
# calls it gates rather than tightening them: adding a word-boundary rule
# would create exactly the false negatives the paragraph above rules out.
#
# Bodies arrive on stdin rather than as arguments for the same reason
# detect-review-request.sh reads stdin -- see its header for the
# MAX_ARG_STRLEN limit that forces it.
#
# Offline tests live in tests/run-detect-bot-mention-tests.sh.
set -euo pipefail

# The default has to stay in step with detect-bot-mention/action.yml's own
# `bot-name` default; tests/run-detect-bot-mention-tests.sh asserts the two
# agree rather than leaving it to a comment (the gha#303 precedent).
MENTION_LIST="${BOT_NAME:-@claude}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STRIP_MARKUP="$SCRIPT_DIR/strip-non-invoking-markup.sh"

# Split the token list once, not per body: it does not vary between bodies.
# Trimming is parameter expansion rather than `echo | xargs` --- xargs also
# applies its own quote and backslash processing, so a token carrying either
# would come back altered, and an unbalanced quote fails the whole script.
declare -a MENTIONS=()
IFS=',' read -ra RAW_TOKENS <<< "$MENTION_LIST"
for token in "${RAW_TOKENS[@]}"; do
  token="${token#"${token%%[![:space:]]*}"}"
  token="${token%"${token##*[![:space:]]}"}"
  [ -n "$token" ] || continue
  MENTIONS+=("$token")
done

if [ "${#MENTIONS[@]}" -eq 0 ]; then
  echo "detect-bot-mention.sh: BOT_NAME held no non-empty tokens: '$MENTION_LIST'" >&2
  exit 2
fi

shopt -s nocasematch

count=0
match=false
# No `break` on a match: stopping early would close the pipe under the writer,
# and `pipefail` in the caller would turn that SIGPIPE into a step failure.
while IFS= read -r -d '' body; do
  count=$((count + 1))
  [ -n "$body" ] || continue
  stripped="$(bash "$STRIP_MARKUP" <<<"$body")"
  for token in "${MENTIONS[@]}"; do
    if [[ "$stripped" == *"$token"* ]]; then
      match=true
      break
    fi
  done
done

if [ "$count" -eq 0 ]; then
  # `printf '%s\n'` rather than `echo`: the usage text itself contains a
  # backslash escape, which `echo` may expand depending on the shell.
  printf '%s\n' "usage: printf '%s\\0' <body> [<body> ...] | detect-bot-mention.sh" >&2
  exit 2
fi

echo "$match"
