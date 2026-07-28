#!/usr/bin/env bash
# Decides whether a comment/review body is an explicit "@claude review"
# request -- i.e. whether claude.yml should route it to the dedicated
# code-review workflow instead of letting the agent answer it itself.
#
# Usage: detect-review-request.sh <body> [<body> ...]
# Prints `true` if ANY argument is a review request, else `false`. Exits 0
# either way, so a caller running under `set -e` can branch on the output.
#
# Why a script rather than an inline `[[ ... =~ ... ]]` in claude.yml: the
# pattern below is no longer a one-liner, it is consulted from two separate
# dispatch paths (the trigger comment and the late-comment rescue scan), and
# a silent regression in it is invisible until a real review request goes
# unanswered. Offline tests live in
# tests/run-detect-review-request-tests.sh (gha#328).
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: detect-review-request.sh <body> [<body> ...]" >&2
  exit 2
fi

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

# `[[:space:][:punct:]]+` (rather than the `[[:space:]]+` this replaced) is
# what admits `@claude, please review` -- the phrasing that went unanswered in
# serodynamics#230 and prompted this. The trailing `[^[:alnum:]]|$` keeps
# `review` a whole word, so `@claude reviewer` is not a request.
PATTERN="@claude[[:space:][:punct:]]+(($POLITE)[[:space:][:punct:]]+)*(re-?)?review([^[:alnum:]]|$)"

# Quoted lines are somebody else's words being cited, not a fresh request:
# replying to a comment via GitHub's "Quote reply" button reproduces its whole
# body prefixed with `> `, which would otherwise re-dispatch a review on every
# such reply.
strip_quotes() {
  sed 's/\r$//; /^[[:space:]]*>/d' <<<"$1"
}

shopt -s nocasematch

for body in "$@"; do
  [ -n "$body" ] || continue
  if [[ "$(strip_quotes "$body")" =~ $PATTERN ]]; then
    echo "true"
    exit 0
  fi
done

echo "false"
