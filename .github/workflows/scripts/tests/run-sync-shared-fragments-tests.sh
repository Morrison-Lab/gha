#!/usr/bin/env bash
# Table test for the "Vendor upstream fragments" step of
# sync-shared-fragments.yml (gha#1796).
#
# It runs the step's own `run:` script, read out of the workflow with Python,
# against a stub `gh` on PATH, in a throwaway directory. It pins the layout
# modes: dest-files writes each file at its explicit destination and stages
# only those paths plus the manifest, the dest-dir mode keeps its flattened
# layout, and each invalid input is refused rather than guessed at.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workflow="$here/../../sync-shared-fragments.yml"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

python3 - "$workflow" "$work/vendor.sh" <<'PY'
import sys
import yaml

wf = yaml.safe_load(open(sys.argv[1]))
steps = wf["jobs"]["sync"]["steps"]
run = next(s["run"] for s in steps if s.get("id") == "fetch")
open(sys.argv[2], "w").write(run)
PY

mkdir "$work/bin"
cat > "$work/bin/gh" <<'STUB'
#!/usr/bin/env bash
case "$*" in
  *"/commits?"*) echo "abc123" ;;
  *"/contents/"*) echo "content of $*" ;;
esac
STUB
chmod +x "$work/bin/gh"

failures=0
nl=$'\n'

# run_case NAME SOURCE_PATHS DEST_DIR DEST_FILES MANIFEST EXPECTED_EXIT
# Leaves the combined output in $out and the working directory in $work/case.
run_case() {
  local name="$1" paths="$2" dir="$3" files="$4" manifest="$5" want="$6"
  rm -rf "$work/case"
  mkdir "$work/case"
  : > "$work/case/github-output"
  out=$(cd "$work/case" && env PATH="$work/bin:$PATH" \
    GITHUB_OUTPUT="$work/case/github-output" \
    GITHUB_SERVER_URL=https://github.com \
    SOURCE_REPO=o/r SOURCE_REF=main \
    SOURCE_PATHS="$paths" DEST_DIR="$dir" DEST_FILES="$files" \
    MANIFEST_PATH="$manifest" bash "$work/vendor.sh" 2>&1)
  got=$?
  if [ "$got" -ne "$want" ]; then
    echo "::error::$name: exit $got, wanted $want"
    failures=$((failures + 1))
    return 1
  fi
}

expect_contains() {
  if ! grep -qF -- "$2" <<< "$3"; then
    echo "::error::$1: missing '$2'"
    failures=$((failures + 1))
  fi
}

# 1. dest-files: explicit destinations, nested directory created, staged paths
#    are exactly the destinations plus the manifest.
pairs="a/offwhite.scss=offwhite.scss${nl}b/x.html=sub/dir/x.html"
if run_case "dest-files" "" "" "$pairs" ".sync/m.json" 0; then
  outputs=$(cat "$work/case/github-output")
  expect_contains "dest-files paths" "paths=offwhite.scss sub/dir/x.html .sync/m.json" "$outputs"
  [ -f "$work/case/sub/dir/x.html" ] || { echo "::error::dest-files: nested destination not written"; failures=$((failures + 1)); }
  manifest=$(cat "$work/case/.sync/m.json")
  expect_contains "dest-files manifest" '"source_path": "b/x.html"' "$manifest"
fi

# 2. source-paths with dest-dir keeps the flattened layout.
if run_case "dest-dir" "a/one.txt${nl}b/two.txt" "vend" "" "" 0; then
  [ -f "$work/case/vend/one.txt" ] && [ -f "$work/case/vend/two.txt" ] \
    || { echo "::error::dest-dir: flattened files not written"; failures=$((failures + 1)); }
  outputs=$(cat "$work/case/github-output")
  expect_contains "dest-dir paths" "paths=vend/one.txt vend/two.txt" "$outputs"
fi

# 3. Refusals, each with its own message.
run_case "both modes" "a" "v" "a=b" "" 1
expect_contains "both modes" "not both" "$out"

run_case "collision" "" "" "a=z${nl}b=z" "" 1
expect_contains "collision" "Destination collision" "$out"

run_case "no equals" "" "" "noequals" "" 1
expect_contains "no equals" "is not source=destination" "$out"

run_case "no input" "" "" "" "" 1
expect_contains "no input" "Set dest-files, or set both source-paths and dest-dir" "$out"

run_case "paths without dir" "a" "" "" "" 1
expect_contains "paths without dir" "Set dest-files, or set both" "$out"

if [ "$failures" -ne 0 ]; then
  echo "::error::$failures assertion(s) failed"
  exit 1
fi
echo "All sync-shared-fragments cases passed."
