#!/usr/bin/env bash
#
# Offline tests for check-secrets/scan-secrets.sh's reporting and gating.
#
# The `secrets` selftest job runs the real composite against this repo's own
# history, which is clean by design and by measurement -- so it always takes
# the finding_count == 0 early return, and everything past it (the `fail`
# normalization's effect, the annotation loop, the step summary, the exit
# code) never executes in CI. Round 1 of gha#385's review found a fail-open
# `fail` bug in exactly that region, and both selftest jobs stayed green.
#
# So drive the script with a STUB gitleaks: a shell script on the same
# GITLEAKS_BIN_DIR path that writes a canned report and exits 0. That
# exercises the real branching offline, with no binary download, no network,
# and no credential-shaped fixture -- the canned report carries only RuleID,
# File, StartLine, Commit, and Fingerprint, never Match or Secret.
#
# Run with: bash check-secrets/tests/test-scan-secrets.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
scan_script="$script_dir/../scan-secrets.sh"

failures=0
case_name=""
work_dir=""
repo_dir=""
stdout_file=""
summary_file=""
scan_status=0

# A full 40-character SHA, so the fingerprint assertions below are about the
# real thing rather than about a shortened stand-in.
FAKE_COMMIT="0bb4984235f2d2247619e729d60fa25fa615dbaf"
FAKE_FINGERPRINT="$FAKE_COMMIT:side-creds.txt:aws-access-token:1"

fail() {
  echo "  FAIL [$case_name]: $*" >&2
  failures=$((failures + 1))
}

assert_status() {
  if [ "$scan_status" != "$1" ]; then
    fail "expected exit status $1, got $scan_status"
  fi
}

assert_stdout_contains() {
  if ! grep -qF -- "$1" "$stdout_file"; then
    fail "$2 -- expected on stdout: $1"
  fi
}

assert_stdout_not_contains() {
  if grep -qF -- "$1" "$stdout_file"; then
    fail "$2 -- expected NOT on stdout: $1"
  fi
}

assert_summary_contains() {
  if ! grep -qF -- "$1" "$summary_file"; then
    fail "$2 -- expected in the step summary: $1"
  fi
}

# Build a throwaway one-commit repo plus a stub gitleaks that writes
# $1 findings into the report path it is handed.
new_case() {
  case_name="$1"
  local finding_count="$2"
  echo "test: $case_name"
  work_dir="$(mktemp -d)"
  repo_dir="$work_dir/repo"
  stdout_file="$work_dir/stdout.txt"
  summary_file="$work_dir/summary.md"
  : > "$summary_file"

  mkdir -p "$repo_dir" "$work_dir/bin"
  git -C "$repo_dir" init -q
  git -C "$repo_dir" config user.email t@example.invalid # phi-allow (throwaway fixture identity, not PHI)
  git -C "$repo_dir" config user.name t
  echo hello > "$repo_dir/README.md"
  git -C "$repo_dir" add README.md
  git -C "$repo_dir" commit -qm base

  if [ "$finding_count" -eq 0 ]; then
    printf '[]\n' > "$work_dir/canned-report.json"
  else
    cat > "$work_dir/canned-report.json" <<EOF
[
 {
  "RuleID": "aws-access-token",
  "StartLine": 1,
  "Match": "REDACTED",
  "Secret": "REDACTED",
  "File": "side-creds.txt",
  "Commit": "$FAKE_COMMIT",
  "Fingerprint": "$FAKE_FINGERPRINT"
 }
]
EOF
  fi

  # The stub reads the --report-path it is given, so the script's own wiring of
  # that flag is exercised rather than assumed.
  cat > "$work_dir/bin/gitleaks" <<'EOF'
#!/usr/bin/env bash
set -eu
report=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--report-path" ]; then report="$arg"; fi
  prev="$arg"
done
if [ -z "$report" ]; then
  echo "stub gitleaks: no --report-path given" >&2
  exit 64
fi
cp "$CANNED_REPORT" "$report"
echo "stub gitleaks: wrote $report"
EOF
  chmod +x "$work_dir/bin/gitleaks"
}

run_scan() {
  env GITLEAKS_BIN_DIR="$work_dir/bin" \
    SECRETS_TARGET="$repo_dir" \
    SECRETS_GENERATED_CONFIG="$work_dir/gitleaks.toml" \
    SECRETS_REPORT_PATH="$work_dir/report.json" \
    GITHUB_STEP_SUMMARY="$summary_file" \
    CANNED_REPORT="$work_dir/canned-report.json" \
    "$@" \
    bash "$scan_script" > "$stdout_file" 2>&1
  scan_status=$?
}

new_case "a clean scan exits 0 and writes no step summary" 0
run_scan
assert_status 0
assert_stdout_contains "No secrets found." "clean message"
if [ -s "$summary_file" ]; then
  fail "expected an empty step summary on a clean run"
fi

new_case "a finding blocks by default" 1
run_scan
assert_status 1
assert_stdout_contains "::error file=side-creds.txt,line=1::" "error annotation"
assert_stdout_contains "possible secret(s) found in git history." "error summary line"

# Round 1 of the gha#385 review found `fail` read fail-open on anything but the
# exact string "true", so these three pin the normalization's EFFECT on the
# exit code, not merely that the variable is read.
new_case "fail: 'True ' still blocks -- fail-closed normalization" 1
run_scan SECRETS_FAIL='True '
assert_status 1

new_case "fail: 'yes' still blocks -- only an explicit false opts out" 1
run_scan SECRETS_FAIL=yes
assert_status 1

new_case "fail: 'FALSE' warns instead of blocking" 1
run_scan SECRETS_FAIL=FALSE
assert_status 0
assert_stdout_contains "::warning file=side-creds.txt,line=1::" "warning-level annotation"
assert_stdout_not_contains "::error" "no error annotation on a warn-only run"

# gha#385 review round 2: .gitleaksignore matches fingerprints by exact lookup,
# so a shortened commit SHA is accepted silently and never suppresses anything.
# Both surfaces must therefore carry the full fingerprint.
new_case "the full fingerprint is reported, never a truncated SHA" 1
run_scan
assert_stdout_contains "$FAKE_FINGERPRINT" "annotation carries the full fingerprint"
assert_summary_contains "$FAKE_FINGERPRINT" "step summary carries the full fingerprint"
assert_stdout_not_contains "in commit ${FAKE_COMMIT:0:12} " "no truncated-SHA phrasing"

# The whole premise of this check is that a value never reaches the log.
new_case "no value-bearing report field is ever printed" 1
run_scan
assert_stdout_not_contains "REDACTED" "Match/Secret are not printed even when redacted"
if grep -qF "REDACTED" "$summary_file"; then
  fail "Match/Secret reached the step summary"
fi

new_case "a shallow clone is refused rather than scanned in part" 0
git clone --depth 1 -q "file://$repo_dir" "$work_dir/shallow"
repo_dir="$work_dir/shallow"
run_scan
assert_status 1
assert_stdout_contains "is a shallow clone" "shallow refusal"
assert_stdout_contains "fetch-depth: 0" "names the fix"

if [ "$failures" -ne 0 ]; then
  echo "$failures assertion(s) failed." >&2
  exit 1
fi

echo "All scan-secrets.sh tests passed."
