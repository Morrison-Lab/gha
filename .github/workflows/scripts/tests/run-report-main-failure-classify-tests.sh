#!/usr/bin/env bash
# Table test for the "Classify the failure" step of report-main-failure.yml.
#
# It runs the step's own `run:` script, not a copy: the script is read out of
# the workflow with Python, and a stub `gh` on PATH stands in for the API. The
# stub hands each page of canned jobs JSON to the real `jq` with the filter the
# script passes through `--jq`, once per page, as `gh api --paginate --jq` does.
# That is what pins the page-reduction bug the review of gha#1774 found: a
# verdict taken from the last page alone fails the two-page cases below.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workflow="$here/../../report-main-failure.yml"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

python3 - "$workflow" "$work/classify.sh" <<'PY'
import sys
import yaml

wf = yaml.safe_load(open(sys.argv[1]))
steps = wf["jobs"]["report"]["steps"]
run = next(s["run"] for s in steps if s.get("id") == "classify")
open(sys.argv[2], "w").write(run)
PY

mkdir "$work/bin"
cat > "$work/bin/gh" <<'STUB'
#!/usr/bin/env bash
# Stub for `gh api <path> --paginate --jq <filter>`: run the filter on each page.
filter=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--jq" ]; then filter="$2"; shift; fi
  shift
done
for page in "$PAGES_DIR"/*.json; do
  jq -r "$filter" "$page"
done
STUB
chmod +x "$work/bin/gh"

failures=0

# run_case NAME EXPECTED PAGE_JSON...
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
  : > "$work/out"
  PAGES_DIR="$dir" PATH="$work/bin:$PATH" GH_TOKEN=x GH_REPO=o/r RUN_ID=1 \
    GITHUB_OUTPUT="$work/out" bash "$work/classify.sh" > /dev/null
  local got
  got="$(sed -n 's/^infra=//p' "$work/out")"
  if [ "$got" = "$expected" ]; then
    echo "ok   $name -> $got"
  else
    echo "FAIL $name: expected infra=$expected, got '$got'"
    failures=$((failures + 1))
  fi
}

checkout_cancelled='{"jobs":[{"conclusion":"failure","steps":[{"name":"Set up job","conclusion":"success"},{"name":"Run actions/checkout@v4","conclusion":"cancelled"}]}]}'
checkout_failed='{"jobs":[{"conclusion":"failure","steps":[{"name":"Run actions/checkout@v4","conclusion":"failure"}]}]}'
setup_failed='{"jobs":[{"conclusion":"failure","steps":[{"name":"Set up job","conclusion":"failure"}]}]}'
test_failed='{"jobs":[{"conclusion":"failure","steps":[{"name":"Run tests","conclusion":"failure"}]}]}'
runner_lost='{"jobs":[{"conclusion":"failure","steps":[]}]}'
timed_out='{"jobs":[{"conclusion":"timed_out","steps":[{"name":"Run actions/checkout@v4","conclusion":"cancelled"}]}]}'
green_only='{"jobs":[{"conclusion":"success","steps":[]}]}'
mixed='{"jobs":[{"conclusion":"failure","steps":[{"name":"Run actions/checkout@v4","conclusion":"failure"}]},{"conclusion":"failure","steps":[{"name":"Run tests","conclusion":"failure"}]}]}'

run_case checkout-cancelled true "$checkout_cancelled"
run_case checkout-failed true "$checkout_failed"
run_case setup-failed true "$setup_failed"
run_case real-test-failure false "$test_failed"
run_case runner-lost true "$runner_lost"
run_case timed-out true "$timed_out"
run_case no-failed-job false "$green_only"
run_case mixed-jobs false "$mixed"
# A real failure on page 1 must not be outvoted by an infra failure on page 2.
run_case real-then-infra-pages false "$test_failed" "$checkout_failed"
run_case infra-then-real-pages false "$checkout_failed" "$test_failed"
run_case infra-on-both-pages true "$checkout_failed" "$runner_lost"

if [ "$failures" -ne 0 ]; then
  echo "$failures case(s) failed."
  exit 1
fi
echo "All report-main-failure classifier cases passed."
