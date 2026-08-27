#!/usr/bin/env bash
# Offline table tests for detect-pr-workflow-edits.sh (gha#598).
#
# The cases that matter are the silent ones: a nested path under
# workflows/scripts, a composite action.yml, and a filename that merely
# contains `.yml`. Each was confirmed to turn this suite red when the
# matcher is widened rather than assumed to.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
detect="$script_dir/../detect-pr-workflow-edits.sh"

failures=0
checked=0

check() {
  local name="$1"
  local files="$2"
  local caller="$3"
  local want_edits="$4"
  local want_caller="$5"
  local want_path="$6"
  local out got_edits got_caller got_path
  out="$(PR_CHANGED_FILES="$files" CALLER_WF_PATH="$caller" bash "$detect")"
  got_edits="$(sed -n 's/^workflow_edits=//p' <<<"$out")"
  got_caller="$(sed -n 's/^caller_edited=//p' <<<"$out")"
  got_path="$(sed -n 's/^edited_path=//p' <<<"$out")"
  checked=$((checked + 1))
  if [ "$got_edits" != "$want_edits" ] || [ "$got_caller" != "$want_caller" ] || [ "$got_path" != "$want_path" ]; then
    echo "FAIL: $name"
    echo "  want: workflow_edits=$want_edits caller_edited=$want_caller edited_path=$want_path"
    echo "  got:  workflow_edits=$got_edits caller_edited=$got_caller edited_path=$got_path"
    failures=$((failures + 1))
  else
    echo "OK   $name"
  fi
}

check "no files" "" ".github/workflows/claude-review.yml" false false ""

check "readme only" $'README.md\nCLAUDE.md' ".github/workflows/claude-review.yml" false false ""

check "selftest workflow" \
  $'README.md\n.github/workflows/_selftest.yml' \
  ".github/workflows/claude-review.yml" true false ".github/workflows/_selftest.yml"

check "caller workflow" \
  ".github/workflows/claude-review.yml" \
  ".github/workflows/claude-review.yml" true true ".github/workflows/claude-review.yml"

check "yaml suffix" \
  ".github/workflows/foo.yaml" \
  ".github/workflows/claude-review.yml" true false ".github/workflows/foo.yaml"

check "nested scripts path is not a workflow" \
  ".github/workflows/scripts/detect-pr-workflow-edits.sh" \
  ".github/workflows/claude-review.yml" false false ""

check "nested yaml under scripts is not a workflow" \
  ".github/workflows/scripts/foo.yml" \
  ".github/workflows/claude-review.yml" false false ""

check "composite action.yml is not a workflow" \
  ".github/actions/run-claude-review-attempt/action.yml" \
  ".github/workflows/claude-review.yml" false false ""

check "filename containing .yml but not a workflow path" \
  "docs/claude-review.yml" \
  ".github/workflows/claude-review.yml" false false ""

check "first matching path wins" \
  $'.github/workflows/_selftest.yml\n.github/workflows/claude.yml' \
  ".github/workflows/claude-review.yml" true false ".github/workflows/_selftest.yml"

check "CRLF files still match" \
  $'.github/workflows/_selftest.yml\r\nREADME.md\r' \
  ".github/workflows/claude-review.yml" true false ".github/workflows/_selftest.yml"

check "empty caller path cannot mark caller_edited" \
  ".github/workflows/claude-review.yml" \
  "" true false ".github/workflows/claude-review.yml"

# Unset PR_CHANGED_FILES must fail rather than report a clean tree.
set +e
err_out="$(CALLER_WF_PATH=".github/workflows/claude-review.yml" bash "$detect" 2>&1)"
err_code=$?
set -e
checked=$((checked + 1))
if [ "$err_code" -ne 0 ] && [[ "$err_out" == *"PR_CHANGED_FILES is unset"* ]]; then
  echo "OK   unset PR_CHANGED_FILES fails closed"
else
  echo "FAIL: unset PR_CHANGED_FILES"
  echo "  want: non-zero exit and 'PR_CHANGED_FILES is unset'"
  echo "  got:  exit $err_code, $err_out"
  failures=$((failures + 1))
fi

if [ "$failures" -gt 0 ]; then
  echo "::error::$failures/$checked detect-pr-workflow-edits test(s) failed"
  exit 1
fi
echo "All $checked detect-pr-workflow-edits cases passed."
