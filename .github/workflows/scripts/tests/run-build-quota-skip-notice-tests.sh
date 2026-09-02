#!/usr/bin/env bash
# Exercises build-quota-skip-notice.sh offline (gha#804).
#
# The claims a reader acts on are what is pinned: which cause the notice
# names, that the wrong cause is NOT named, that the API message reaches the
# body verbatim and stays inside the blockquote, that the delivery
# classifier's marker survives every branch, and that the collapse step's
# run-ID capture still matches.
#
# Usage: bash .github/workflows/scripts/tests/run-build-quota-skip-notice-tests.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build_script="$script_dir/../build-quota-skip-notice.sh"
run_url="https://github.com/Morrison-Lab/gha/actions/runs/987654321"

failures=0
checks=0

check() {
  local label="$1" expected="$2" actual="$3"
  checks=$((checks + 1))
  if [[ "$expected" != "$actual" ]]; then
    printf 'FAIL: %s\n  expected: %s\n  actual:   %s\n' "$label" "$expected" "$actual"
    failures=$((failures + 1))
  fi
}
contains() { [[ "$1" == *"$2"* ]] && echo true || echo false; }

build() {
  # $1 reason, $2 message (may be empty)
  QUOTA_REASON="$1" QUOTA_MESSAGE="${2:-}" RUN_URL="$run_url" bash "$build_script"
}

# --- every reason: marker, alert header, run URL, blockquote-only lines -----
for reason in missing-secret rejected-at-door midrun-429 unknown ''; do
  got="$(build "$reason" '')"
  label="${reason:-<empty>}"
  check "$label: alert header" true "$(contains "$got" '> [!WARNING]')"
  check "$label: delivery-classifier marker" true "$(contains "$got" 'Claude review skipped')"
  check "$label: run URL" true "$(contains "$got" "$run_url")"
  check "$label: every line is blockquoted" "0" "$(grep -cv '^>' <<<"$got")"
  check "$label: no message line without a message" false "$(contains "$got" 'API message:')"
done

# --- missing-secret: names the absent secret, never the quota/429 story -----
got="$(build missing-secret '')"
check "missing-secret: names the absent credential" true "$(contains "$got" 'no API credential is configured')"
check "missing-secret: does not claim a 429" false "$(contains "$got" '429')"
check "missing-secret: does not say a credential is configured" false "$(contains "$got" 'A credential is configured')"

# --- rejected-at-door: credential present, request refused before any work --
got="$(build rejected-at-door '')"
check "rejected-at-door: names the door rejection" true "$(contains "$got" 'rejected the first request')"
check "rejected-at-door: says a credential is configured" true "$(contains "$got" 'A credential is configured')"
check "rejected-at-door: does not say no secret is configured" false "$(contains "$got" 'No `CLAUDE_CODE_OAUTH_TOKEN`')"

# --- midrun-429: the case gha#804 was filed over ----------------------------
api_msg="You've hit your session limit · resets 10:50pm (UTC)"
got="$(build midrun-429 "$api_msg")"
check "midrun-429: names the mid-run 429" true "$(contains "$got" 'returned 429 part-way through')"
check "midrun-429: says the credential was accepted" true "$(contains "$got" 'was accepted')"
check "midrun-429: does not say no secret is configured" false "$(contains "$got" 'secret is configured')"
check "midrun-429: quotes the API message verbatim" true "$(contains "$got" "> API message: $api_msg")"
check "midrun-429: cites gha#520" true "$(contains "$got" 'gha#520')"

# --- a message carrying newlines stays inside the blockquote -----------------
got="$(build midrun-429 $'first line\nsecond line\r\nthird')"
check "multiline message: no line escapes the blockquote" "0" "$(grep -cv '^>' <<<"$got")"
check "multiline message: collapsed onto the message line" true "$(contains "$got" 'API message: first line second line  third')"

# --- a message on the door-rejection path is quoted too ---------------------
got="$(build rejected-at-door 'Invalid API key')"
check "rejected-at-door: quotes a captured message" true "$(contains "$got" '> API message: Invalid API key')"

# --- unknown / empty reason: the pre-gha#804 wording, unchanged --------------
got="$(build '' '')"
check "empty reason: falls back to the disjunction" true "$(contains "$got" 'No `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` secret is configured, or account API quota is exhausted')"
got="$(build bogus-reason '')"
check "unrecognized reason: falls back to the disjunction" true "$(contains "$got" 'or account API quota is exhausted')"

# --- the collapse step's capture pattern still finds the run id -------------
got="$(build midrun-429 "$api_msg")"
extracted="$(jq -n -r --arg body "$got" '((($body | capture("actions/runs/(?<r>[0-9]+)").r)?) // "")')"
check "collapse regex captures the run id" "987654321" "$extracted"

# --- RUN_URL is required -----------------------------------------------------
if QUOTA_REASON=midrun-429 RUN_URL= bash "$build_script" >/dev/null 2>"$script_dir/.err.$$"; then
  check "missing RUN_URL must fail" fail pass
else
  check "missing RUN_URL must fail" fail fail
fi
check "missing RUN_URL names the input" "1" "$(grep -c 'RUN_URL is required' "$script_dir/.err.$$" || true)"
rm -f "$script_dir/.err.$$"

if [[ "$failures" -ne 0 ]]; then
  echo "::error::$failures/$checks build-quota-skip-notice assertion(s) failed"
  exit 1
fi
echo "All $checks build-quota-skip-notice assertions passed."
