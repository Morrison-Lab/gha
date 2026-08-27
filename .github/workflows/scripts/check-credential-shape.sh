#!/usr/bin/env bash
# Decide whether an API credential secret is structurally usable as an HTTP
# Authorization header value, BEFORE a review run spends money finding out
# (gha#686).
#
# Why this exists. claude-code-review.yml's pre-flight check only ever asked
# whether a credential secret was non-EMPTY. A secret that is set but carries
# the wrong content -- a PEM private key, a JSON credential file, anything
# pasted as a block -- passes that test, so the run starts, the SDK rejects the
# request at the door, and check-review-execution.sh classifies the result as
# `hard-error`. That kind's PR comment says the cause "lies elsewhere" and
# points at the run log, which is true and unhelpful: the actual cause is a
# repository secret only an admin can repair, and nothing on the thread says
# so. Observed on UCD-SERG/serodynamics#298, where the SDK's own result read
# "Invalid Authorization header value from CLAUDE_CODE_OAUTH_TOKEN: it contains
# a line break at character 56 (2931 characters on 62 lines)".
#
# Why the rule is INTERIOR whitespace rather than any whitespace. An HTTP
# header value may not contain whitespace at all, so the strictest reading
# would reject a merely trailing newline too -- which `gh secret set < file`
# produces routinely, and which today's consumers may well be running on
# successfully if the action trims before sending. Rejecting that would newly
# redden reviews that currently work, converting a hardening change into an
# outage. Whitespace that survives trimming cannot be a stray newline and
# cannot be trimmed away by anyone downstream, so it is the half of the
# condition that is unambiguously broken. Erring toward running the review is
# right here: a missed detection costs one badly-worded failure comment, the
# same one consumers get today, while a false detection blocks review entirely.
#
# Why it does not repair the value. The observed case was 2931 characters on 62
# lines, which is not a token with a stray newline in it -- it is different
# content entirely. Stripping the whitespace would send a credential nobody
# chose and turn a nameable configuration defect into an opaque rejection, so
# this fails fast and names the remedy instead (fail-fast, and this repo's own
# "no silent fallback" guidance).
#
# The value arrives through the environment, never on argv: argv is readable
# via `ps` / /proc/<pid>/cmdline, the same reasoning trigger-bugbot-review.sh
# records for its own API key.
#
# Inputs (environment):
#   CREDENTIAL_VALUE  the secret's value; may be empty
#   CREDENTIAL_NAME   the secret's name, for the message (default: the secret)
#
# Contract (stdout), read by fixed line offset like this repo's other
# classifiers:
#   line 1  malformed=true|false
#   line 2  detail=<single line, safe to print: never any part of the value>
#
# An EMPTY value is reported as malformed=false. "Not configured" is a
# different condition with its own pre-flight branch and its own message, and
# answering it here would give one condition two voices.
set -euo pipefail

VALUE="${CREDENTIAL_VALUE-}"
NAME="${CREDENTIAL_NAME:-the credential secret}"

# Strip leading, then trailing, whitespace. Whatever survives is interior.
trimmed="${VALUE#"${VALUE%%[![:space:]]*}"}"
trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"

if [[ -z "$trimmed" || "$trimmed" != *[[:space:]]* ]]; then
  printf 'malformed=false\n'
  printf 'detail=\n'
  exit 0
fi

# Diagnostics only: counts and a position, never a substring of the value.
# The SDK's own rejection message prints exactly these figures, so they reveal
# nothing it does not already reveal, and they are what makes the difference
# between "a stray newline" and "the wrong file was pasted in" visible.
chars="${#VALUE}"
lines=1
newlines="${VALUE//[!$'\n']/}"
lines=$(( ${#newlines} + 1 ))
prefix="${trimmed%%[[:space:]]*}"
position=$(( ${#prefix} + 1 ))

# Pluralize, because this string reaches a PR comment rather than a log line.
line_word=lines
[[ "$lines" == 1 ]] && line_word=line
char_word=characters
[[ "$chars" == 1 ]] && char_word=character

printf 'malformed=true\n'
printf 'detail=%s contains whitespace at character %s of its trimmed value (%s %s on %s %s), so it cannot be sent as an HTTP Authorization header.\n' \
  "$NAME" "$position" "$chars" "$char_word" "$lines" "$line_word"
