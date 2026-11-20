#!/usr/bin/env bash
# Table test for the "Close the failure issue" step of report-main-failure.yml
# (gha#1776).
#
# It runs the step's own `run:` script, read out of the workflow with Python,
# against a stub `gh`. The stub runs the script's `--jq` filter on each page of
# canned issues, as `gh api --paginate --jq` does, and logs every
# `gh issue comment` and `gh issue close` call, so each case asserts exactly
# which issues were closed.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workflow="$here/../../report-main-failure.yml"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

python3 - "$workflow" "$work/close.sh" <<'PY'
import sys
import yaml

wf = yaml.safe_load(open(sys.argv[1]))
steps = wf["jobs"]["close"]["steps"]
run = next(s["run"] for s in steps if s.get("name") == "Close the failure issue")
open(sys.argv[2], "w").write(run)
PY

mkdir "$work/bin"
cat > "$work/bin/gh" <<'STUB'
#!/usr/bin/env bash
# Stub: `gh api ... --jq F` runs F on each page; `gh issue comment|close N`
# appends "comment N" or "close N" to $CALLS.
if [ "$1" = "api" ]; then
  filter=""
  while [ $# -gt 0 ]; do
    if [ "$1" = "--jq" ]; then filter="$2"; shift; fi
    shift
  done
  for page in "$PAGES_DIR"/*.json; do
    jq -r "$filter" "$page"
  done
  exit 0
fi
if [ "$1" = "issue" ]; then
  echo "$2 $3" >> "$CALLS"
  exit 0
fi
exit 1
STUB
chmod +x "$work/bin/gh"

failures=0

issue() { printf '{"number":%s,"title":"%s"}' "$1" "$2"; }
pr() { printf '{"number":%s,"title":"%s","pull_request":{}}' "$1" "$2"; }

# run_case NAME EXPECTED_CALLS PAGE_JSON...
# EXPECTED_CALLS is the logged calls joined with spaces.
run_case() {
  local name="$1" expected="$2"
  shift 2
  local dir="$work/case-$name"
  mkdir -p "$dir"
  local i=0
  for page in "$@"; do
    i=$((i + 1))
    printf '%s' "$page" > "$dir/$(printf '%02d' "$i").json"
  done
  : > "$work/calls"
  PAGES_DIR="$dir" CALLS="$work/calls" PATH="$work/bin:$PATH" GH_TOKEN=x \
    GH_REPO=o/r TITLE="Main CI failing: Check links" RUN_URL=https://example.test/run \
    HEAD_SHA=abc bash "$work/close.sh" > /dev/null
  local got
  got="$(paste -sd' ' "$work/calls")"
  if [ "$got" = "$expected" ]; then
    echo "ok   $name"
  else
    echo "::error::$name: expected [$expected], got [$got]"
    failures=$((failures + 1))
  fi
}

run_case "the matching issue is commented on and closed" \
  "comment 5 close 5" \
  "[$(issue 5 'Main CI failing: Check links'),$(issue 6 'Something else')]"
run_case "no matching issue closes nothing" \
  "" \
  "[$(issue 6 'Something else')]"
run_case "a title that only starts the same is not a match" \
  "" \
  "[$(issue 7 'Main CI failing: Check links extra')]"
run_case "a pull request with the title is not closed" \
  "" \
  "[$(pr 8 'Main CI failing: Check links')]"
run_case "a match on the second page is found" \
  "comment 9 close 9" \
  "[$(issue 1 'Other')]" "[$(issue 9 'Main CI failing: Check links')]"
run_case "duplicates are all closed" \
  "comment 3 close 3 comment 4 close 4" \
  "[$(issue 3 'Main CI failing: Check links'),$(issue 4 'Main CI failing: Check links')]"

if [ "$failures" -gt 0 ]; then
  echo "::error::$failures report-main-failure close case(s) failed"
  exit 1
fi
echo "All report-main-failure close cases passed."
