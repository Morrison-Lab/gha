#!/usr/bin/env bash
# Exercises detect-bot-mention.sh offline, mirroring
# run-detect-review-request-tests.sh's pattern. Wired into _selftest.yml's
# `review-fail-check` job (gha#342).
#
# Read the `false` rows as the whole point of the script and the `true` rows as
# the guard rails around them. Skipping is the only behaviour change this
# script can cause, and a wrongly skipped run means a genuine request is
# silently ignored -- so every phrasing that should still invoke the agent is
# pinned here too, not just the ones that should not.
#
# The fixtures are single-quoted where they contain backticks: those are the
# Markdown under test, not shell syntax.
# shellcheck disable=SC2016
#
# Usage: bash .github/workflows/scripts/tests/run-detect-bot-mention-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
detect_script="$repo_root/.github/workflows/scripts/detect-bot-mention.sh"

# "<expected>|<body>" -- `|` never appears in a body below.
cases=(
  # A plain mention invokes the agent, with or without a request attached.
  'true|@claude fix the failing test'
  'true|@claude'
  'true|Thanks. @claude can you take a look?'
  # `contains()` in the workflow `if:` is case-insensitive, and this must not
  # be narrower than the gate it backs.
  'true|@CLAUDE fix the failing test'
  # The gha#342 case: describing the bot is not addressing it.
  'false|the trigger is `@claude` and it has no notion of Markdown'
  'false|write `@claude review` to dispatch a review'
  $'false|Example caller comment:\n\n```\n@claude fix this\n```'
  $'false|~~~yaml\nif: contains(github.event.comment.body, @claude)\n~~~'
  # A quote-reply reproduces the whole body prefixed with `> `.
  $'false|> @claude fix the failing test\n> thanks'
  # Mixed: quoting a mention while also making a real request must still run.
  # This is the row that stops the stripping from becoming a way to silence
  # the bot.
  $'true|You asked for `@claude` to be quoted safely.\n\n@claude please do that'
  $'true|```\n@claude fix this\n```\n\n@claude actually do it'
  # No mention at all. The workflow `if:` would not have started the job, so
  # this only pins that the script agrees rather than guessing.
  'false|please review this when you get a chance'
  'false|'
)

failures=0
for case in "${cases[@]}"; do
  want="${case%%|*}"
  body="${case#*|}"
  got="$(printf '%s\0' "$body" | bash "$detect_script")"
  if [[ "$got" == "$want" ]]; then
    echo "OK   detect-bot-mention.sh ${body@Q} -> $got"
  else
    echo "::error::detect-bot-mention.sh ${body@Q}: expected $want but got $got"
    failures=$((failures + 1))
  fi
done

# The composite passes four bodies at once (comment, review, issue body, issue
# title), so a mention in any one of them has to count. The `issues` event
# gates on the title as well as the body, and a title carrying the mention
# with a quoted body is the case that would otherwise be skipped wrongly.
if [[ "$(printf '%s\0' "" "" 'see `@claude`' "@claude fix this" | bash "$detect_script")" != "true" ]]; then
  echo "::error::detect-bot-mention.sh missed a mention in a later body"
  failures=$((failures + 1))
else
  echo "OK   detect-bot-mention.sh matches a mention in any body"
fi

# All four bodies empty is what every non-mention event looks like, and the
# composite always passes four. It must report false, not exit 2.
if [[ "$(printf '%s\0' "" "" "" "" | bash "$detect_script")" != "false" ]]; then
  echo "::error::detect-bot-mention.sh should report false for four empty bodies"
  failures=$((failures + 1))
else
  echo "OK   detect-bot-mention.sh reports false for four empty bodies"
fi

# No bodies at all can only mean a miswired caller, so fail loudly rather than
# reporting a confident "false" that would silently suppress every run.
if bash "$detect_script" </dev/null >/dev/null 2>&1; then
  echo "::error::detect-bot-mention.sh should exit non-zero on empty stdin"
  failures=$((failures + 1))
else
  echo "OK   detect-bot-mention.sh rejects empty stdin"
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of $(( ${#cases[@]} + 3 )) detect-bot-mention case(s) did not behave as expected"
  exit 1
fi
echo "All $(( ${#cases[@]} + 3 )) detect-bot-mention cases behaved as expected."
