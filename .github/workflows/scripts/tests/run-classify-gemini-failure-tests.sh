#!/usr/bin/env bash
# Exercises classify-gemini-failure.sh offline, mirroring the pattern the
# other script suites in this directory use (see
# run-classify-push-failure-tests.sh). Wired into _selftest.yml's
# `gemini-review-fail-check` job.
#
# Usage: bash .github/workflows/scripts/tests/run-classify-gemini-failure-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
classify="$repo_root/.github/workflows/scripts/classify-gemini-failure.sh"

failures=0
total=0

# A quota/rate-limit rejection, in the shape the Gemini API's own JSON error
# envelope uses.
quota_json=$(cat <<'EOF'
{"error":{"code":429,"message":"Resource has been exhausted (e.g. check quota).","status":"RESOURCE_EXHAUSTED"}}
EOF
)

# An auth rejection -- an invalid or revoked API key.
auth_json=$(cat <<'EOF'
{"error":{"code":403,"message":"API key not valid. Please pass a valid API key.","status":"PERMISSION_DENIED"}}
EOF
)

# The wording most directly relevant to this issue: a suspended project.
# Deliberately close to the notice's own phrasing, not invented independently
# of it -- the classifier has to recognize the actual failure this was built
# for, not just a plausible-looking substitute.
suspended_text='Your API access has been suspended for violating the Gemini API Additional Terms of Service.'

# Plain rate-limit wording with no JSON envelope at all -- run-gemini-cli's
# `error` output can be raw stderr text when stderr wasn't valid JSON.
rate_limit_text='Error: rate limit exceeded, please try again later.'

# A genuine bug: a malformed prompt/settings error. Must classify as `other`
# -- this is the failure class that must still fail loudly, not be swallowed
# as a graceful skip.
malformed_json=$(cat <<'EOF'
{"error":{"code":400,"message":"Invalid JSON payload received. Unknown name \"settings\" at 'request'.","status":"INVALID_ARGUMENT"}}
EOF
)

# A network/transient failure with no recognizable marker at all.
network_text='Error: connect ETIMEDOUT 142.250.80.95:443'

# check_kind <name> <error-output> <expected kind>
check_kind() {
  local name="$1" err="$2" want="$3" got
  total=$((total + 1))
  got="$(printf '%s\n' "$err" | bash "$classify" - | sed -n '1s/^kind=//p')"
  if [[ "$got" == "$want" ]]; then
    echo "OK   $name"
  else
    echo "::error::$name: expected kind '$want' but got '$got'"
    failures=$((failures + 1))
  fi
}

# check_advice <name> <error-output> <substring that must appear> <mode: has|lacks>
check_advice() {
  local name="$1" err="$2" needle="$3" mode="${4:-has}" out
  total=$((total + 1))
  out="$(printf '%s\n' "$err" | bash "$classify" -)"
  if [[ "$mode" == "has" ]] && grep -qF -- "$needle" <<<"$out"; then
    echo "OK   $name"
  elif [[ "$mode" == "lacks" ]] && ! grep -qF -- "$needle" <<<"$out"; then
    echo "OK   $name"
  else
    echo "::error::$name: expected output to $mode '$needle'"
    failures=$((failures + 1))
  fi
}

check_kind "quota (429 / RESOURCE_EXHAUSTED)"    "$quota_json"      quota-or-auth
check_kind "auth (403 / PERMISSION_DENIED)"      "$auth_json"       quota-or-auth
check_kind "suspended project"                   "$suspended_text"  quota-or-auth
check_kind "rate limit, no JSON envelope"        "$rate_limit_text" quota-or-auth
check_kind "malformed request (genuine bug)"     "$malformed_json"  other
check_kind "network timeout"                     "$network_text"    other
check_kind "empty error output"                  ""                 other

# The graceful-skip advice must say "not retried" -- the whole point of this
# script is stopping an automatic retry against a suspended/rate-limited key.
check_advice "quota advice says not retried" "$quota_json" "not retried" has
check_advice "suspended advice says not retried" "$suspended_text" "not retried" has

# A genuine bug must NOT be told "not retried automatically" -- that line is
# specific to the quota/auth class; a malformed-prompt bug isn't something a
# retry would ever fix either way, but the advice text must not conflate the
# two failure classes.
check_advice "generic failure omits the quota framing" "$malformed_json" "not retried" lacks

# The output contract the composite action parses, by line: `kind=`,
# `headline=`, a blank, then advice. The composite reads each by fixed
# offset, so a reordering here breaks it silently.
total=$((total + 1))
out="$(printf '%s\n' "$quota_json" | bash "$classify" -)"
if [[ "$(sed -n '1p' <<<"$out")" == kind=* ]] &&
   [[ "$(sed -n '2p' <<<"$out")" == headline=* ]] &&
   [[ -z "$(sed -n '3p' <<<"$out")" ]] &&
   [[ -n "$(tail -n +4 <<<"$out")" ]]; then
  echo "OK   output shape (kind / headline / blank / advice)"
else
  echo "::error::output shape: expected kind, headline, blank line, then advice"
  failures=$((failures + 1))
fi

# The headline reaches an ::error::/::warning:: annotation, which is a single
# line.
total=$((total + 1))
if [[ "$(sed -n '2s/^headline=//p' <<<"$out" | wc -l)" -eq 1 ]]; then
  echo "OK   headline is a single line"
else
  echo "::error::headline must be a single line to be usable in ::error::/::warning::"
  failures=$((failures + 1))
fi

# The advice must not embed the raw error output itself -- that's the calling
# composite action's job (see classify-gemini-failure.sh's own header comment
# for why), so the classifier's own output must not contain the raw JSON it
# was given.
total=$((total + 1))
if ! grep -qF 'RESOURCE_EXHAUSTED' <<<"$(tail -n +4 <<<"$out")"; then
  echo "OK   advice does not embed the raw error output"
else
  echo "::error::advice embedded the raw error output; that belongs to the caller"
  failures=$((failures + 1))
fi

# Reading from a file is the path the composite uses when it is not piping.
total=$((total + 1))
tmp_err="$(mktemp)"
printf '%s\n' "$quota_json" > "$tmp_err"
if [[ "$(bash "$classify" "$tmp_err" | sed -n '1s/^kind=//p')" == "quota-or-auth" ]]; then
  echo "OK   reads an error-output file argument"
else
  echo "::error::reading the error output from a file argument did not classify correctly"
  failures=$((failures + 1))
fi
rm -f "$tmp_err"

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of $total classify-gemini-failure case(s) did not behave as expected"
  exit 1
fi
echo "All $total classify-gemini-failure cases behaved as expected."
