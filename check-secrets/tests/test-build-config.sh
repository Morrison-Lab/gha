#!/usr/bin/env bash
#
# Offline tests for check-secrets/build-gitleaks-config.sh.
#
# The generated TOML decides which findings are suppressed, so a bug here
# silently weakens the scan rather than breaking it -- which is why the
# generator is a script with tests rather than inline shell in action.yml.
#
# Run with: bash check-secrets/tests/test-build-config.sh
#
# Deliberately free of any credential-shaped fixture: the check-secrets selftest
# job scans this repo's own history, and a realistic dummy token here would
# force an allowlist entry to keep it green.
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build_script="$script_dir/../build-gitleaks-config.sh"

failures=0
case_name=""
work_dir=""
repo_dir=""
out_config=""
build_status=0

fail() {
  echo "  FAIL [$case_name]: $*" >&2
  failures=$((failures + 1))
}

assert_contains() {
  if ! grep -qF -- "$1" "$out_config"; then
    fail "$2 -- expected to find: $1"
  fi
}

assert_not_contains() {
  if grep -qF -- "$1" "$out_config"; then
    fail "$2 -- expected NOT to find: $1"
  fi
}

assert_status() {
  if [ "$build_status" != "$1" ]; then
    fail "expected exit status $1, got $build_status"
  fi
}

assert_status_nonzero() {
  if [ "$build_status" -eq 0 ]; then
    fail "expected a non-zero exit status, got 0"
  fi
}

# Start a case with a throwaway repo root; tests that need pre-existing files
# create them under $repo_dir before calling run_build.
new_case() {
  case_name="$1"
  echo "test: $case_name"
  work_dir="$(mktemp -d)"
  repo_dir="$work_dir/repo"
  out_config="$work_dir/gitleaks.toml"
  mkdir -p "$repo_dir/.github"
}

# Run the generator with only the SECRETS_* variables this case names, so no
# case can leak an input into the next one.
run_build() {
  env SECRETS_TARGET="$repo_dir" SECRETS_GENERATED_CONFIG="$out_config" "$@" \
    bash "$build_script" > /dev/null 2>&1
  build_status=$?
  # Always leave a file behind so an assertion after a refused build reads an
  # empty config rather than erroring on a missing path.
  [ -f "$out_config" ] || : > "$out_config"
}

new_case "no inputs extends the default ruleset"
run_build
assert_status 0
assert_contains "useDefault = true" "default extend"
assert_not_contains "[[allowlists]]" "no allowlist emitted"

new_case "paths-ignore becomes a paths allowlist, split on commas and newlines"
run_build SECRETS_PATHS_IGNORE='check-secrets/tests/, one/two

# a comment
three/four'
assert_status 0
assert_contains "[[allowlists]]" "allowlist table"
assert_contains "paths = [" "paths key"
assert_contains "'''check-secrets/tests/'''," "first pattern"
assert_contains "'''one/two'''," "comma-separated pattern, trimmed"
assert_contains "'''three/four'''," "newline-separated pattern"
assert_not_contains "a comment" "comment line dropped"
assert_not_contains "''''''," "blank line dropped"

new_case "allowlist-file becomes a match-targeted regexes allowlist"
printf '# comment\n\nsome-regex-one\n  some-regex-two  \n' > "$work_dir/allow.txt"
run_build SECRETS_ALLOWLIST_FILE="$work_dir/allow.txt"
assert_status 0
assert_contains 'regexTarget = "match"' "match target"
assert_contains "'''some-regex-one'''," "first regex"
assert_contains "'''some-regex-two'''," "second regex, trimmed"
assert_not_contains "comment" "comment line dropped"

new_case "an explicit config is extended by path, not by useDefault"
printf '[extend]\nuseDefault = true\n' > "$work_dir/custom.toml"
run_build SECRETS_CONFIG="$work_dir/custom.toml"
assert_status 0
assert_contains "path = '''$work_dir/custom.toml'''" "extend by path"
assert_not_contains "useDefault" "no useDefault alongside path"

new_case ".gitleaks.toml and .github/secrets-allowlist.txt are auto-detected"
printf '[extend]\nuseDefault = true\n' > "$repo_dir/.gitleaks.toml"
printf 'auto-detected-regex\n' > "$repo_dir/.github/secrets-allowlist.txt"
run_build
assert_status 0
assert_contains "path = '''$repo_dir/.gitleaks.toml'''" "auto-detected config"
assert_contains "'''auto-detected-regex'''," "auto-detected allowlist"

# Confirmed to fail when the generator's reject_toml_delimiter call is stubbed
# out: the build then exits 0 and writes the delimiter-bearing pattern into the
# config, where it would truncate the array and silently change which findings
# are suppressed.
new_case "a pattern containing the TOML literal delimiter is refused"
run_build SECRETS_PATHS_IGNORE="fine/path,has'''delimiter"
assert_status_nonzero
assert_not_contains "has'''delimiter" "no config entry written"

new_case "a missing allowlist file is an error, not an empty allowlist"
run_build SECRETS_ALLOWLIST_FILE="$work_dir/nonexistent.txt"
assert_status_nonzero

new_case "a missing config file is an error, not a silent fall back to default"
run_build SECRETS_CONFIG="$work_dir/nonexistent.toml"
assert_status_nonzero

if [ "$failures" -ne 0 ]; then
  echo "$failures assertion(s) failed." >&2
  exit 1
fi

echo "All build-gitleaks-config.sh tests passed."
