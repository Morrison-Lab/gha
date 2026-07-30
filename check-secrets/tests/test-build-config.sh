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
stderr_file=""
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
  stderr_file="$work_dir/stderr.txt"
  mkdir -p "$repo_dir/.github"
  : > "$stderr_file"
}

# Run the generator with only the SECRETS_* variables this case names, so no
# case can leak an input into the next one.
run_build() {
  env SECRETS_TARGET="$repo_dir" SECRETS_GENERATED_CONFIG="$out_config" "$@" \
    bash "$build_script" > /dev/null 2> "$stderr_file"
  build_status=$?
  # Always leave a file behind so an assertion after a refused build reads an
  # empty config rather than erroring on a missing path.
  [ -f "$out_config" ] || : > "$out_config"
}

assert_stderr_contains() {
  if ! grep -qF -- "$1" "$stderr_file"; then
    fail "$2 -- expected on stderr: $1"
  fi
}

assert_stderr_not_contains() {
  if grep -qF -- "$1" "$stderr_file"; then
    fail "$2 -- expected NOT on stderr: $1"
  fi
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

# gha#385 review: the allowlist file is documented as one regex per line, and
# a comma inside a regex is ordinary syntax. Comma-splitting it turned
# `AKIA[0-9A-Z]{16,20}` into two fragments that both compile, so nothing
# errored -- the suppression just stopped matching while `20}` became its own
# unanchored allowlist entry. Confirmed to fail when split_patterns is passed
# `commas` for this path.
new_case "a bounded quantifier in the allowlist file survives intact"
printf 'AKIA[0-9A-Z]{16,20}\n' > "$work_dir/allow.txt"
run_build SECRETS_ALLOWLIST_FILE="$work_dir/allow.txt"
assert_status 0
assert_contains "'''AKIA[0-9A-Z]{16,20}'''," "quantifier kept whole"
assert_not_contains "'''20}'''," "no fragment entry"

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

# gha#385 review: `**` fails to compile in Go, but a trailing `/*` is a valid
# regex, and gitleaks matches allowlist paths unanchored -- so `docs/*`
# silently suppresses every path containing `docs`. Warn rather than reject,
# since `.*\.pem` is a legitimate pattern ending in a repetition operator.
new_case "a glob-shaped path pattern is warned about, and a regex one is not"
run_build SECRETS_PATHS_IGNORE='docs/*,tests/fixtures/**,^src/.*\.pem$'
assert_status 0
assert_stderr_contains "'docs/*' from the paths-ignore input looks like a glob" "trailing /* warned"
assert_stderr_contains "'tests/fixtures/**' from the paths-ignore input looks like a glob" "** warned"
assert_stderr_not_contains "^src/" "a plain regex is not warned about"
assert_contains "'''docs/*'''," "the pattern is still emitted, not dropped"

# gha#385 review round 2: a bare `docs*` matched neither the `**` arm nor the
# trailing-`/*` arm, yet is strictly MORE over-broad than `docs/*` -- it also
# matches `my-doc-secret.env` and `x/documents/key.pem`.
new_case "a bare word-star glob is warned about too"
run_build SECRETS_PATHS_IGNORE='docs*'
assert_status 0
assert_stderr_contains "'docs*' from the paths-ignore input looks like a glob" "bare word* warned"

# The trailing-`*` arm keys on the character being quantified, so ordinary
# regex repetition stays quiet. Without that, the warning fires constantly and
# stops being read.
new_case "ordinary regex repetition does not trigger the glob warning"
run_build SECRETS_PATHS_IGNORE='.*\.pem$
[a-z]*/keys
\w*\.env'
assert_status 0
assert_stderr_not_contains "looks like a glob" "no false positives on real regexes"

new_case "an allowlist-file regex ending in a repetition operator is not warned about"
printf 'secret-.*\n' > "$work_dir/allow.txt"
run_build SECRETS_ALLOWLIST_FILE="$work_dir/allow.txt"
assert_status 0
assert_stderr_not_contains "looks like a glob" "glob check does not apply to allowlist regexes"

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
