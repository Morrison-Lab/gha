#!/usr/bin/env bash
# Exercises build-self-review-skip-notice.sh offline, verifying notice formatting
# and the collapse step's run-ID matching contract (actions/runs/(?<r>[0-9]+)).
# Wired into _selftest.yml's test suite (gha#441, gha#598).
#
# Usage: bash .github/workflows/scripts/tests/run-build-self-review-skip-notice-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
build_script="$repo_root/.github/workflows/scripts/build-self-review-skip-notice.sh"

failures=0

# Test 1: Restore-failure skip (gha#598)
wf_path=".github/workflows/claude-code-review.yml"
run_url="https://github.com/Morrison-Lab/gha/actions/runs/987654321"

got="$(bash "$build_script" "$wf_path" "$run_url" "$wf_path")"

if [[ "$got" == *"> [!WARNING]"* ]]; then
  echo "OK   build-self-review-skip-notice.sh contains warning alert header"
else
  echo "::error::build-self-review-skip-notice.sh output missing '> [!WARNING]'"
  failures=$((failures + 1))
fi

if [[ "$got" == *"restoring default-branch workflow files failed"* ]]; then
  echo "OK   build-self-review-skip-notice.sh names a restore failure"
else
  echo "::error::build-self-review-skip-notice.sh output missing restore-failure phrasing"
  failures=$((failures + 1))
fi

if [[ "$got" == *"gha#598"* ]]; then
  echo "OK   build-self-review-skip-notice.sh cites gha#598"
else
  echo "::error::build-self-review-skip-notice.sh output missing gha#598"
  failures=$((failures + 1))
fi

if [[ "$got" == *"$wf_path"* ]]; then
  echo "OK   build-self-review-skip-notice.sh contains workflow path '$wf_path'"
else
  echo "::error::build-self-review-skip-notice.sh output missing workflow path '$wf_path'"
  failures=$((failures + 1))
fi

if [[ "$got" == *"$run_url"* ]]; then
  echo "OK   build-self-review-skip-notice.sh contains run URL '$run_url'"
else
  echo "::error::build-self-review-skip-notice.sh output missing run URL '$run_url'"
  failures=$((failures + 1))
fi

# Apply the collapse step's literal capture pattern for actions/runs/(?<r>[0-9]+)
if command -v jq >/dev/null 2>&1; then
  extracted_run_id="$(jq -n -r --arg body "$got" '((($body | capture("actions/runs/(?<r>[0-9]+)").r)?) // "")')"
else
  extracted_run_id="$(printf '%s\n' "$got" | grep -oE 'actions/runs/[0-9]+' | cut -d'/' -f3 || true)"
fi
if [[ "$extracted_run_id" == "987654321" ]]; then
  echo "OK   collapse step regex correctly captured run ID '987654321' from notice body"
else
  echo "::error::collapse step regex failed to extract run ID '987654321'; got '$extracted_run_id'"
  failures=$((failures + 1))
fi

# Test 2: A different edited path still appears; the third arg is ignored.
other_wf=".github/workflows/_selftest.yml"
caller_wf=".github/workflows/claude-review.yml"
got2="$(bash "$build_script" "$other_wf" "$run_url" "$caller_wf")"

if [[ "$got2" == *"$other_wf"* ]] && [[ "$got2" == *"restoring default-branch workflow files failed"* ]]; then
  echo "OK   build-self-review-skip-notice.sh names the edited path on a non-caller workflow"
else
  echo "::error::build-self-review-skip-notice.sh did not name '$other_wf' in the restore-failure notice"
  failures=$((failures + 1))
fi

# Test 3: Missing arguments usage check
set +e
err_output="$(bash "$build_script" 2>&1)"
exit_code=$?
set -e

if [[ $exit_code -ne 0 ]] && [[ "$err_output" == *"usage: build-self-review-skip-notice.sh"* ]]; then
  echo "OK   build-self-review-skip-notice.sh fails with usage message when arguments missing"
else
  echo "::error::build-self-review-skip-notice.sh did not fail with expected usage error"
  failures=$((failures + 1))
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures build-self-review-skip-notice test(s) failed"
  exit 1
fi
echo "All build-self-review-skip-notice cases behaved as expected."
