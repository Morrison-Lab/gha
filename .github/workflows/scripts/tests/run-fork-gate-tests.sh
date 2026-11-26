#!/usr/bin/env bash
# Tests for the fork refusal in claude.yml's "Decide whether this run should
# proceed" step (gha#1217). The step is inline YAML, so this suite extracts
# the lines between its begin and end markers and runs them against a stub
# `gh`, one case per row.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
WORKFLOW="$ROOT/.github/workflows/claude.yml"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Strip the YAML block indentation from the marked lines.
sed -n '/# fork-gate begin/,/# fork-gate end/p' "$WORKFLOW" \
  | sed -E 's/^ {10}//' > "$TMP/gate.sh"
if ! grep -q 'RUNNER_ENVIRONMENT' "$TMP/gate.sh"; then
  echo "::error::could not extract the gate block from $WORKFLOW"
  exit 1
fi

mkdir -p "$TMP/bin"
cat > "$TMP/bin/gh" <<'EOF'
#!/usr/bin/env bash
# Stub: print $STUB_HEAD_REPO as the PR's head repository, or fail when asked.
[ "${STUB_FAIL:-}" = 1 ] && exit 1
printf '%s\n' "${STUB_HEAD_REPO:-}"
EOF
chmod +x "$TMP/bin/gh"

fails=0
# run_case NAME RUNNER_ENV PR_NUMBER HEAD_REPO DEDUP STUB_FAIL WANT_EXIT WANT_OUTPUT
# WANT_OUTPUT is the GITHUB_OUTPUT file's lines joined with spaces.
run_case() {
  local name="$1" runner="$2" pr="$3" head="$4" dedup="$5" stub_fail="$6"
  local want_exit="$7" want_out="$8"
  local out="$TMP/out" got_exit got_out
  : > "$out"
  PATH="$TMP/bin:$PATH" RUNNER_ENVIRONMENT="$runner" PR_NUMBER="$pr" \
    STUB_HEAD_REPO="$head" STUB_FAIL="$stub_fail" DEDUP_SKIP="$dedup" \
    REPO=o/r GITHUB_OUTPUT="$out" bash "$TMP/gate.sh" >/dev/null 2>&1
  got_exit=$?
  got_out="$(paste -sd' ' "$out")"
  if [ "$got_exit" = "$want_exit" ] && [ "$got_out" = "$want_out" ]; then
    echo "ok   $name"
  else
    echo "::error::$name: expected exit $want_exit [$want_out], got exit $got_exit [$got_out]"
    fails=$((fails + 1))
  fi
}

run_case "same-repo PR on a self-hosted runner proceeds" \
  self-hosted 7 o/r "" "" 0 "skip=false"
run_case "fork PR on a self-hosted runner is refused" \
  self-hosted 7 fork/r "" "" 0 "skip=true fork_refused=true"
run_case "a deleted fork (no head repo) is refused" \
  self-hosted 7 "" "" "" 0 "skip=true fork_refused=true"
run_case "an API failure fails the step rather than proceeding" \
  self-hosted 7 o/r "" 1 1 ""
run_case "fork PR on a GitHub-hosted runner proceeds" \
  github-hosted 7 fork/r "" "" 0 "skip=false"
run_case "an issue (no PR) on a self-hosted runner proceeds without a lookup" \
  self-hosted "" fork/r "" 1 0 "skip=false"
run_case "the dedup marker still stands the run down" \
  self-hosted 7 fork/r true "" 0 "skip=true"

if [ "$fails" -gt 0 ]; then
  echo "::error::$fails fork-gate case(s) failed"
  exit 1
fi
echo "All fork-gate cases passed."
