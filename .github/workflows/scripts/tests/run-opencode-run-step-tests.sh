#!/usr/bin/env bash
# Offline tests for the "Run OpenCode review" step's bounded retry loop
# (gha#600): extract the step's `run:` block from the workflow YAML and run
# it against a stub installer and a stub opencode CLI, asserting the
# exitcode/attempts outputs per scenario.
#
# The load-bearing case is (b): an auth-style failure must NOT retry -- the
# positive signature match is what keeps auth/quota failures single-shot,
# so this suite fails if that negative direction regresses. The other cases
# pin the loop bounds and the happy path.
#
# The YAML is extracted by line scan rather than a YAML library because the
# review-fail-check job installs only bash/jq (the same constraint as the
# check-new-line-breaks defaults test).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
workflow="$here/../../opencode-code-review.yml"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# --- extraction ---------------------------------------------------------
awk '
  /^      - name: Run OpenCode review$/ { in_step = 1 }
  in_step && /^        run: \|/ { in_body = 1; next }
  in_body && /^          / { sub(/^          /, ""); print; next }
  in_body { exit }
' "$workflow" > "$tmp/run-step.sh"
if [[ ! -s "$tmp/run-step.sh" ]]; then
  echo "FAIL: could not extract the Run OpenCode review run block" >&2
  exit 1
fi
bash -n "$tmp/run-step.sh" || { echo "FAIL: extracted script does not parse" >&2; exit 1; }

# --- stubs --------------------------------------------------------------
# Stub curl: emits an "installer" that writes a fake opencode CLI which
# fails per its state file: one line per attempt naming the failure kind to
# emit ("ok", "net", "auth").
mkdir "$tmp/bin"
cat > "$tmp/bin/curl" <<'STUB'
#!/usr/bin/env bash
cat <<'INSTALLER'
mkdir -p "$HOME/.opencode/bin"
cat > "$HOME/.opencode/bin/opencode" <<'FAKE'
#!/usr/bin/env bash
state="$RETRY_TEST_STATE"
n=$(( $(cat "$state.count" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$state.count"
kind=$(sed -n "${n}p" "$state")
case "$kind" in
  net)  echo "Error: Provider finish_reason: network_error" >&2; exit 1 ;;
  auth) echo "Error: 401 Unauthorized" >&2; exit 1 ;;
  ok)   printf '# review\n\n### Verdict\nAPPROVE\n' ; exit 0 ;;
  *)    echo "unknown kind '$kind'" >&2; exit 70 ;;
esac
FAKE
chmod +x "$HOME/.opencode/bin/opencode"
INSTALLER
STUB
chmod +x "$tmp/bin/curl"

if ! command -v timeout >/dev/null 2>&1; then
  cat > "$tmp/bin/timeout" <<'TIMEOUT_STUB'
#!/usr/bin/env bash
shift
exec "$@"
TIMEOUT_STUB
  chmod +x "$tmp/bin/timeout"
fi

run_scenario() {
  local name="$1" attempts="$2" state_file="$3"
  mkdir -p "$tmp/home-$name"
  (
    export HOME="$tmp/home-$name"
    export PATH="$tmp/bin:$PATH"
    export OPENCODE_API_KEY=test-key OPENCODE_VERSION=0 OPENCODE_MODEL=m \
      OPENCODE_ATTEMPTS="$attempts" RETRY_SLEEP_SECONDS=0 \
      PROMPT_FILE=/dev/null DIFF_FILE=/dev/null \
      RETRY_TEST_STATE="$state_file" \
      GITHUB_OUTPUT="$tmp/gho-$name.txt"
    cd "$(mktemp -d)"
    # The extracted step script exits non-zero by design in several
    # scenarios; capture that as data rather than letting it abort the
    # suite here.
    bash "$tmp/run-step.sh" || true
  ) > "$tmp/out-$name.txt" 2>&1
}

assert_outputs() {
  local name="$1" want_rc="$2" want_attempts="$3"
  local got_rc got_att
  got_rc=$(sed -n 's/^exitcode=//p' "$tmp/gho-$name.txt")
  got_att=$(sed -n 's/^attempts=//p' "$tmp/gho-$name.txt")
  if [[ "$got_rc" != "$want_rc" || "$got_att" != "$want_attempts" ]]; then
    echo "FAIL [$name]: expected exitcode=$want_rc attempts=$want_attempts, got exitcode=$got_rc attempts=$got_att" >&2
    sed 's/^/    /' "$tmp/out-$name.txt" >&2
    exit 1
  fi
  echo "pass [$name] exitcode=$got_rc attempts=$got_att"
}

# --- cases ----------------------------------------------------------------
printf 'net\nnet\nok\n'   > "$tmp/s-recover.tsv"
run_scenario recover 3 "$tmp/s-recover.tsv"
assert_outputs recover 0 3

printf 'auth\nauth\nauth\n' > "$tmp/s-auth.tsv"
run_scenario auth 3 "$tmp/s-auth.tsv"
assert_outputs auth 1 1

printf 'net\nnet\nnet\nnet\nnet\n' > "$tmp/s-exhaust.tsv"
run_scenario exhaust 3 "$tmp/s-exhaust.tsv"
assert_outputs exhaust 1 3

printf 'ok\n'             > "$tmp/s-clean.tsv"
run_scenario clean 3 "$tmp/s-clean.tsv"
assert_outputs clean 0 1

printf 'ok\n'             > "$tmp/s-badinput.tsv"
run_scenario badinput 99 "$tmp/s-badinput.tsv"
# Validation fires inside the captured region before any attempt runs, so
# rc=2 with attempts still emitted (defined) and no CLI invocation.
assert_outputs badinput 2 1

echo "All opencode run-step retry scenarios passed."
