#!/usr/bin/env bash
#
# Offline tests for check-extra/check-extra.R.
#
# The check-extra selftest job exercises the real composite against a
# generated fixture, which always takes the happy path (green examples,
# tests, vignettes, README render). Everything that is silent when reversed
# -- skip vs fail of a missing surface, a freshness fail, an unknown check
# name, main() env plumbing, a warning() in a test, a defaults drift
# between action.yml and the reusable workflow -- lives here so it actually
# runs.
#
# Run with: bash check-extra/tests/test-check-extra.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
r_script="$script_dir/../check-extra.R"
action_yml="$script_dir/../action.yml"
workflow_yml="$script_dir/../../.github/workflows/check-extra.yml"

failures=0
case_name=""

fail() {
  echo "  FAIL [$case_name]: $*" >&2
  failures=$((failures + 1))
}

# --- The two declared check-readme-freshness defaults agree ---------------
# Declared in action.yml and the reusable workflow. A drift here means a
# consumer of the reusable workflow gets a different freshness gate from a
# consumer of the composite, with nothing red -- the gha#303 precedent.
case_name="declared check-readme-freshness defaults agree"
action_default="$(
  awk '
    $1 == "check-readme-freshness:" { in_input = 1; next }
    in_input && $1 == "default:" {
      print $2
      exit
    }
  ' "$action_yml"
)"
workflow_default="$(
  awk '
    $1 == "check-readme-freshness:" { in_input = 1; next }
    in_input && $1 == "default:" {
      print $2
      exit
    }
  ' "$workflow_yml"
)"
# action.yml stores strings ('true'); workflow_call booleans are bare true.
action_norm="${action_default#\'}"
action_norm="${action_norm%\'}"
if [ -z "$action_default" ] || [ -z "$workflow_default" ]; then
  fail "could not read check-readme-freshness default (action='$action_default' workflow='$workflow_default')"
elif [ "$action_norm" != "$workflow_default" ]; then
  fail "action.yml default $action_default != workflow default $workflow_default"
else
  echo "  ok - declared check-readme-freshness defaults agree ($workflow_default)"
fi

# --- R tests, skipped only when Rscript is not on PATH --------------------
# The selftest job runs this after the composite has installed R, so the
# skip is for a laptop without R, not for CI.
if ! command -v Rscript >/dev/null 2>&1; then
  echo "Rscript not on PATH; skipping R-level tests."
  if [ "$failures" -ne 0 ]; then
    echo "$failures failure(s)." >&2
    exit 1
  fi
  exit 0
fi

r_out="$(mktemp)"
if ! Rscript "$script_dir/test-check-extra.R" >"$r_out" 2>&1; then
  echo "  FAIL [R tests]:" >&2
  cat "$r_out" >&2
  failures=$((failures + 1))
else
  cat "$r_out"
fi
rm -f "$r_out"

if [ "$failures" -ne 0 ]; then
  echo "$failures failure(s)." >&2
  exit 1
fi
echo "All check-extra offline tests passed."
exit 0
