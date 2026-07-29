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

# BOT_NAME points the same gate at another bot's mention; gemini.yml passes
# '@gemini,@gemini-cli'. Both tokens of a multi-token list have to match, and
# @claude must stop matching once BOT_NAME names another bot -- otherwise a
# `@claude` comment would also wake the Gemini agent. The stripping behaviour
# is unchanged by BOT_NAME, so a quoted mention of the named bot still skips.
bot_cases=(
  "@gemini,@gemini-cli|true|@gemini fix this"
  "@gemini,@gemini-cli|true|please look at this, @gemini-cli"
  "@gemini,@gemini-cli|false|@claude fix this"
  '@gemini|false|see `@gemini` in the docs'
  # Whitespace around a token is trimmed, not split on.
  "@ai , @gemini|true|@gemini fix this"
)
for case in "${bot_cases[@]}"; do
  bot="${case%%|*}"
  rest="${case#*|}"
  want="${rest%%|*}"
  body="${rest#*|}"
  got="$(printf '%s\0' "$body" | BOT_NAME="$bot" bash "$detect_script")"
  if [[ "$got" == "$want" ]]; then
    echo "OK   detect-bot-mention.sh BOT_NAME=${bot@Q} ${body@Q} -> $got"
  else
    echo "::error::detect-bot-mention.sh BOT_NAME=${bot@Q} ${body@Q}: expected $want but got $got"
    failures=$((failures + 1))
  fi
done

# A BOT_NAME holding no usable token is a miswired caller. This gate's only
# effect is to skip, so reporting "false" here would silence every run for a
# typo in the caller's input; exit non-zero instead.
if printf '%s\0' "@claude fix this" | BOT_NAME=" , " bash "$detect_script" >/dev/null 2>&1; then
  echo "::error::detect-bot-mention.sh should exit non-zero on an empty BOT_NAME list"
  failures=$((failures + 1))
else
  echo "OK   detect-bot-mention.sh rejects an empty BOT_NAME list"
fi

# The script's own BOT_NAME fallback and the action's `bot-name` default are
# declared in two files, so assert they agree rather than trusting a comment
# (the gha#303 precedent for defaults declared more than once). Parsed with a
# line scan because this job installs no YAML library.
action_yml="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../actions/detect-bot-mention" && pwd)/action.yml"
action_default="$(awk '/^  bot-name:/ {found=1} found && /^    default:/ {gsub(/^    default:[[:space:]]*/, ""); gsub(/^['"'"'"]|['"'"'"]$/, ""); print; exit}' "$action_yml")"
script_default="$(awk '/^MENTION_LIST=/ {sub(/^MENTION_LIST="\$\{BOT_NAME:-/, ""); sub(/\}"$/, ""); print; exit}' "$detect_script")"
if [[ -z "$action_default" ]]; then
  echo "::error::detect-bot-mention/action.yml declares no default for bot-name"
  failures=$((failures + 1))
elif [[ "$action_default" != "$script_default" ]]; then
  echo "::error::bot-name default drift: action.yml has ${action_default@Q}, script has ${script_default@Q}"
  failures=$((failures + 1))
else
  echo "OK   detect-bot-mention bot-name default agrees across action.yml and the script"
fi

total=$(( ${#cases[@]} + ${#bot_cases[@]} + 5 ))
if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of $total detect-bot-mention case(s) did not behave as expected"
  exit 1
fi
echo "All $total detect-bot-mention cases behaved as expected."
