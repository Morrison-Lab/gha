#!/usr/bin/env bash
# Exercises check-credential-shape.sh offline against a table of credential
# values (gha#686). Wired into _selftest.yml's `review-fail-check` job.
#
# The negative cases are the ones to keep if this suite is ever trimmed. A
# validator that answers `true` too eagerly BLOCKS review entirely for a
# consumer whose credential works fine today, which is strictly worse than the
# badly-worded failure comment this change set out to improve -- so the cases
# proving a valid token, a trailing newline, and an empty value all pass
# through untouched are what bound the blast radius.
#
# Usage: bash .github/workflows/scripts/tests/run-check-credential-shape-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
check_script="$repo_root/.github/workflows/scripts/check-credential-shape.sh"

failures=0
cases=0

# run <name> <expected-malformed> <value>
run() {
  local name="$1" want="$2" value="$3" out got
  cases=$((cases + 1))
  out="$(CREDENTIAL_VALUE="$value" CREDENTIAL_NAME=CLAUDE_CODE_OAUTH_TOKEN bash "$check_script")"
  got="$(sed -n '1s/^malformed=//p' <<< "$out")"
  if [[ "$got" != "$want" ]]; then
    echo "::error::$name: expected malformed=$want but got malformed=$got"
    failures=$((failures + 1))
    return
  fi
  # The two-line contract is read by fixed line offset in the calling step, so
  # a reordering would break the caller silently. Assert the shape, not just
  # the verdict -- the same reasoning run-classify-push-failure-tests.sh gives.
  if [[ "$(wc -l <<< "$out")" != "2" ]]; then
    echo "::error::$name: expected a 2-line contract, got $(wc -l <<< "$out") lines"
    failures=$((failures + 1))
    return
  fi
  if ! sed -n '2p' <<< "$out" | grep -q '^detail='; then
    echo "::error::$name: line 2 is not a detail= line"
    failures=$((failures + 1))
    return
  fi
  # A detail line reaching a PR comment must never carry the secret itself.
  # This is the assertion that survives a rewording of the message.
  if [[ "$want" == "true" ]]; then
    local detail
    detail="$(sed -n '2s/^detail=//p' <<< "$out")"
    if [[ -z "$detail" ]]; then
      echo "::error::$name: malformed verdict with an empty detail line"
      failures=$((failures + 1))
      return
    fi
    local first_token="${value%%[[:space:]]*}"
    if [[ -n "$first_token" && "$detail" == *"$first_token"* ]]; then
      echo "::error::$name: detail line leaked part of the credential value"
      failures=$((failures + 1))
      return
    fi
  fi
  echo "OK   $name -> malformed=$got"
}

# --- must NOT be flagged -------------------------------------------------
# A plain single-line token, the overwhelmingly common case.
run 'plain token'            false 'sk-ant-oat01-AbC123-xyz'
# `gh secret set < file` leaves a trailing newline routinely. Flagging it
# would redden reviews that work today; see the script's own header.
run 'trailing newline'       false $'sk-ant-oat01-AbC123-xyz\n'
run 'leading newline'        false $'\nsk-ant-oat01-AbC123-xyz'
run 'surrounding spaces'     false '   sk-ant-oat01-AbC123-xyz   '
# Empty is "not configured", which is a different condition with its own
# pre-flight branch. Answering it here would give one condition two voices.
run 'empty value'            false ''
run 'whitespace-only value'  false $'  \n  '
# An API key rather than an OAuth token: same validator, same verdict.
run 'anthropic api key'      false 'sk-ant-api03-0123456789abcdef'

# --- must be flagged -----------------------------------------------------
# The observed UCD-SERG/serodynamics#298 shape: a multi-line block pasted
# into the secret (there, 2931 characters on 62 lines).
run 'pasted PEM block'       true  $'-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----\n'
run 'pasted json blob'       true  $'{\n  "token": "sk-ant-oat01-abc"\n}\n'
run 'interior newline'       true  $'sk-ant-oat01-AbC123\nxyz'
run 'interior carriage ret'  true  $'sk-ant-oat01-AbC123\rxyz'
run 'interior space'         true  'sk-ant-oat01 AbC123'
run 'interior tab'           true  $'sk-ant-oat01\tAbC123'
# Interior whitespace still counts when the value is ALSO padded, i.e. the
# trimming must not swallow the interior break along with the padding.
run 'padded and interior'    true  $'  sk-ant-oat01\nAbC123  '

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of $cases credential-shape case(s) did not behave as expected"
  exit 1
fi
echo "All $cases credential-shape cases behaved as expected."
