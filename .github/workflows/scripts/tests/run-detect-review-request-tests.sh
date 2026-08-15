#!/usr/bin/env bash
# Exercises detect-review-request.sh offline, mirroring
# run-sum-costs-tests.sh's pattern. Wired into _selftest.yml's
# `review-fail-check` job (gha#339).
#
# The cases below are the contract, not a sample: claude.yml suppresses the
# agent's own prose reply whenever this script returns true, so both a missed
# request and a misfire are user-visible, and neither shows up until a real
# comment hits the workflow.
#
# Usage: bash .github/workflows/scripts/tests/run-detect-review-request-tests.sh
set -euo pipefail

# The suites below exercise the scripts' DEFAULT behavior, which reads
# BOT_NAME from the environment -- so an ambient value silently changes what
# is being tested. `anthropics/claude-code-action` exports BOT_NAME=claude[bot]
# in its environment, and under it this suite reported a hard abort with zero cases run
# instead of its real result. Clear it here so a hand run and a CI run agree;
# the BOT_NAME-specific cases below set it inline per case.
unset BOT_NAME

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
detect_script="$repo_root/.github/workflows/scripts/detect-review-request.sh"

# "<expected>|<body>" -- `|` never appears in a body below.
cases=(
  # Requests the previous `@claude[[:space:]]+review` pattern already caught.
  "true|@claude review"
  "true|@claude  review"
  $'true|Thanks for the fix.\n\n@claude review'
  # Punctuated and polite phrasings it missed (serodynamics#276, #277).
  "true|@claude, please review"
  "true|@claude, review"
  # Whitespace BEFORE the punctuation, which is how the mention is actually
  # typed in the wild (verbatim shape from UCD-SERG/serodynamics#230). The
  # unspaced forms above are pinned and this one was not, so nothing recorded
  # that the `[[:space:][:punct:]]+` separator class -- rather than a
  # punctuation-then-space ordering -- is what admits it.
  "true|@claude , please review"
  "true|@claude please review this PR"
  "true|@claude can you review this?"
  "true|@claude could you please review"
  "true|@claude would you review the latest push"
  "true|@claude kindly review"
  "true|@claude pls review"
  "true|@claude plz review"
  "true|@claude re-review please"
  "true|@CLAUDE Review"
  # An object pointing back at the PR is fine, and so is prose on later lines.
  "true|@claude review this"
  "true|@claude review again"
  "true|@claude please review the latest changes"
  $'true|@claude review\n\nI pushed a fix for the flaky test.'
  $'true|@claude, please review\n\nthanks!'
  # ... but an object naming something to go look at is a request to the
  # agent, not a dispatch keyword. Accepting these was the cost of admitting
  # the polite lead-ins above: they route a question to the read-only reviewer
  # and suppress the agent's own reply to it (gha#346).
  "false|@claude can you review this and also fix the failing test?"
  "false|@claude please review my reasoning in the issue description above"
  "false|@claude, can you review why the coverage job is flaky and patch it?"
  "false|@claude could you review the docs and update them if wrong"
  # Known false negatives, pinned so the contract is explicit rather than
  # discovered. Both are pure review requests carrying no instruction to the
  # agent, and both dispatched before the tail was constrained. Widening
  # TAIL_WORD would recover them; these cases make that a deliberate decision
  # instead of a drift (gha#346).
  "false|@claude review the changes I just pushed"
  "false|@claude please review when you get a chance"
  # A third, from a real thread: the mention carries a non-review task, and the
  # review is asked for in a separate later sentence with no mention of its
  # own. False because a request must sit adjacent to the mention, which is
  # right -- but unlike the two above, this one was written by someone who did
  # want a review and did not get one (UCD-SERG/serodynamics#230). Pinned so
  # that relaxing adjacency, or letting a later line carry the request, stays a
  # deliberate decision rather than a drift.
  $'false|@claude, Please acknowledge and fix the comments left in this review.\r\n\r\nAlso, please review this pull request.'
  # CRLF is what GitHub actually delivers, and the pattern anchors on a bare
  # newline, so the normalizer has to strip the CRs for any of the above to
  # hold in production (gha#346).
  $'true|@claude review\r\nI pushed a fix.'
  $'false|> @claude review\r\n> yes\r'
  # Quote-replies cite somebody else's request; they are not a fresh one.
  "false|> @claude review"
  $'false|> @claude review\n>\n> ...as I said above'
  $'true|> @claude review\n\n@claude review'
  # Code spans and fences are the same idea as a blockquote, one and two
  # constructs down: standard Markdown for "this is a literal string, not
  # something I mean". Documenting the accepted phrasings used to dispatch a
  # review, so writing this very table down cost a run (gha#344).
  'false|the accepted phrasings are `@claude review` and `@claude, review`'
  # The span has to end the line, or the trailing prose alone makes this
  # false and the case proves nothing about run-length matching.
  'false|the double-backtick form is ``@claude review``'
  $'false|An example caller comment:\n\n```\n@claude review\n```'
  $'false|~~~\n@claude, please review\n~~~'
  # ... but a genuine request in the prose still dispatches, even when the
  # same comment also quotes the phrasing. Stripping must not become a way to
  # suppress a real request that happens to sit near an example.
  $'true|@claude review\n\nFor reference the other accepted form is `@claude, review`.'
  $'true|Here is the failing config:\n\n```yaml\nreview: true\n```\n\n@claude please review'
  # An @claude request that merely contains the word "review". Matching these
  # would swallow the agent's reply to the question actually being asked.
  "false|@claude the review workflow is broken, can you fix it?"
  "false|@claude I have addressed your review comments"
  "false|@claude take another look at the review job"
  # `review` must be a whole word.
  "false|@claude reviewer assignments are wrong"
  # No mention at all, and a mention with no request.
  "false|Please review this."
  "false|@claude what does this function do?"
  "false|"
  # The agent's own trailing attribution line, which every comment it posts
  # carries. That makes it the highest-frequency body in the wild containing
  # the token, and the one where a regression costs the most: matching it would
  # be a self-trigger loop rather than a stray run, since the agent would be
  # dispatching a review off its own footer. False because the word after the
  # mention is not a request keyword. (Shape from a real bot comment on
  # UCD-SERG/serodynamics#230; its em dash is written `--` here per this repo's
  # ASCII-punctuation rule, which the matcher is indifferent to.)
  'false|<sub>-- posted by @claude post-step from [workflow run](https://example.invalid/r)</sub>'
  # BOT_NAME defaults to @claude alone, so another bot's mention is not a
  # request until a caller passes it (the BOT_NAME table below).
  "false|@gemini review"
)

failures=0
for case in "${cases[@]}"; do
  want="${case%%|*}"
  body="${case#*|}"
  got="$(printf '%s\0' "$body" | bash "$detect_script")"
  if [[ "$got" == "$want" ]]; then
    echo "OK   detect-review-request.sh ${body@Q} -> $got"
  else
    echo "::error::detect-review-request.sh ${body@Q}: expected $want but got $got"
    failures=$((failures + 1))
  fi
done

# Multiple bodies: claude.yml passes the comment and review bodies together,
# and its late-comment scan appends every comment posted after the trigger,
# so `any of` matters.
if [[ "$(printf '%s\0' "not a request" "@claude please review" | bash "$detect_script")" != "true" ]]; then
  echo "::error::detect-review-request.sh did not match a review request in a later body"
  failures=$((failures + 1))
else
  echo "OK   detect-review-request.sh matches a request in any body"
fi

# A body larger than Linux's per-argument MAX_ARG_STRLEN (131072 bytes). The
# first implementation passed bodies as positional arguments, so a single
# emoji-heavy comment -- well inside GitHub's 65536-character cap, but up to
# 256 KiB in 4-byte UTF-8 -- failed `execve` with E2BIG and reddened the whole
# claude job (gha#341 review). Reverting the stdin rewrite makes this case
# fail; nothing else in the table reaches the limit.
huge="$(head -c 200000 /dev/zero | tr '\0' 'x')"
if [[ "$(printf '%s\0' "$huge" "@claude please review" | bash "$detect_script")" != "true" ]]; then
  echo "::error::detect-review-request.sh failed on a body larger than MAX_ARG_STRLEN"
  failures=$((failures + 1))
else
  echo "OK   detect-review-request.sh handles a body larger than MAX_ARG_STRLEN"
fi

# No bodies at all can only mean a miswired caller, so fail loudly rather
# than reporting a confident "false".
if bash "$detect_script" </dev/null >/dev/null 2>&1; then
  echo "::error::detect-review-request.sh should exit non-zero on empty stdin"
  failures=$((failures + 1))
else
  echo "OK   detect-review-request.sh rejects empty stdin"
fi

# BOT_NAME lets a caller point the same matcher at another bot's mention;
# gemini.yml passes '@gemini,@gemini-cli'. The table covers both tokens of a
# multi-token list, the hyphenated token (which relies on `[:punct:]` already
# containing `-` in the separator class), and the negative that keeps the list
# from being a superset: @claude is NOT a request once BOT_NAME names another
# bot, or a `@gemini review` and a `@claude review` on the same PR would both
# wake the same agent.
bot_cases=(
  "@gemini,@gemini-cli|true|@gemini review"
  "@gemini,@gemini-cli|true|@gemini-cli review"
  "@gemini,@gemini-cli|true|@gemini, please review this"
  "@gemini,@gemini-cli|false|@claude review"
  "@gemini,@gemini-cli|false|@gemini what does this do?"
  # Whitespace around a token is trimmed rather than split on: ' @ai ' is one
  # alternative, not two.
  "@ai , @ai-review|true|@ai review"
  "@ai|true|@ai-review"
)
for case in "${bot_cases[@]}"; do
  bot="${case%%|*}"
  rest="${case#*|}"
  want="${rest%%|*}"
  body="${rest#*|}"
  got="$(printf '%s\0' "$body" | BOT_NAME="$bot" bash "$detect_script")"
  if [[ "$got" == "$want" ]]; then
    echo "OK   detect-review-request.sh BOT_NAME=${bot@Q} ${body@Q} -> $got"
  else
    echo "::error::detect-review-request.sh BOT_NAME=${bot@Q} ${body@Q}: expected $want but got $got"
    failures=$((failures + 1))
  fi
done

# A BOT_NAME holding no usable token is a miswired caller, not a body that
# fails to match, so it exits non-zero rather than reporting "false".
if printf '%s\0' "@claude review" | BOT_NAME=" , " bash "$detect_script" >/dev/null 2>&1; then
  echo "::error::detect-review-request.sh should exit non-zero on an empty BOT_NAME list"
  failures=$((failures + 1))
else
  echo "OK   detect-review-request.sh rejects an empty BOT_NAME list"
fi

# Tokens are spliced into an ERE, so a token that is not a plain @mention is
# rejected up front. Both directions matter and neither is cosmetic: a
# metacharacter silently widens what matches, and an unbalanced bracket makes
# the regex fail to compile inside an `if` --- which `set -e` exempts, so it
# would return false for every comment forever with nothing in the log. The
# hyphen case is the guard rail: `@gemini-cli` is legitimate and must survive.
invalid_bots=(
  '@bot.name'      # `.` would match any character
  '@bot+'          # `+` would quantify
  '@bot*'          # `*` would quantify
  '@bot['          # unbalanced bracket: regex fails to compile
  '@bot('          # unbalanced paren: same
  'claude'         # no leading @
  '@-bot'          # a login cannot start with a hyphen
  '@'              # bare @
)
for bad in "${invalid_bots[@]}"; do
  if printf '%s\0' "@claude review" | BOT_NAME="$bad" bash "$detect_script" >/dev/null 2>&1; then
    echo "::error::detect-review-request.sh should reject BOT_NAME token ${bad@Q}"
    failures=$((failures + 1))
  else
    echo "OK   detect-review-request.sh rejects BOT_NAME token ${bad@Q}"
  fi
done

# The script's own BOT_NAME fallback and the action's `bot-name` default are
# declared in two files, so assert they agree rather than trusting a comment
# (the gha#303 precedent for defaults declared more than once). Parsed with a
# line scan because this job installs no YAML library.
action_yml="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../actions/detect-review-request" && pwd)/action.yml"
action_default="$(awk '/^  bot-name:/ {found=1} found && /^    default:/ {gsub(/^    default:[[:space:]]*/, ""); gsub(/^['"'"'"]|['"'"'"]$/, ""); print; exit}' "$action_yml")"
script_default="$(awk '/^BOT_NAME_INPUT=/ {sub(/}"$/, "", $0); sub(/^BOT_NAME_INPUT="\$\{BOT_NAME:-/, ""); sub(/\}"$/, ""); print; exit}' "$detect_script")"
if [[ -z "$action_default" ]]; then
  echo "::error::detect-review-request/action.yml declares no default for bot-name"
  failures=$((failures + 1))
elif [[ "$action_default" != "$script_default" ]]; then
  echo "::error::bot-name default drift: action.yml has ${action_default@Q}, script has ${script_default@Q}"
  failures=$((failures + 1))
else
  echo "OK   detect-review-request bot-name default agrees across action.yml and the script"
fi
# Verify that a stripper failure causes detect-review-request.sh to fail loudly (exit non-zero)
tmp_failing_stripper="$(mktemp "${TMPDIR:-/tmp}/failing_stripper.XXXXXX")"
chmod +x "$tmp_failing_stripper"
cat <<'EOF' > "$tmp_failing_stripper"
#!/usr/bin/env bash
echo "REcompile() - panic" >&2
exit 100
EOF

if printf '%s\0' "@claude review" | STRIP_MARKUP="$tmp_failing_stripper" bash "$detect_script" >/dev/null 2>&1; then
  echo "::error::detect-review-request.sh should fail loudly when stripper fails"
  failures=$((failures + 1))
else
  echo "OK   detect-review-request.sh fails loudly when stripper fails"
fi
rm -f "$tmp_failing_stripper"

total=$(( ${#cases[@]} + ${#bot_cases[@]} + ${#invalid_bots[@]} + 6 ))
if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of $total detect-review-request case(s) did not behave as expected"
  exit 1
fi
echo "All $total detect-review-request cases behaved as expected."

