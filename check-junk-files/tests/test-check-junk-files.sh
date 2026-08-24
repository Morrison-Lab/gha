#!/usr/bin/env bash
#
# Offline tests for check-junk-files/check-junk-files.sh.
#
# The `junk-files` selftest job runs the real composite against this repo's own
# tree, which is clean -- so it always takes the zero-match early return, and
# everything past it (the annotation loop, the step summary, the `fail`
# normalization's effect, the exit code) never runs in CI. That is the same
# structural gap check-secrets records for its own selftest job, and the same
# remedy: drive the script directly against throwaway git repos built in
# $TMPDIR, so the branching executes offline.
#
# The cases worth keeping if this is ever trimmed are the four NEGATIVE ones,
# because each pins a decision that is silent when reversed:
#
#   * a force-added file listed in the repo's own .gitignore is NOT reported
#     (passing --exclude-standard would report it),
#   * `paths-ignore: 'vendor/'` really exempts the directory (implementing it
#     as gitignore `!` lines would exempt nothing, silently),
#   * an empty pattern set is an ERROR (dropping the guard makes it a green
#     check that examined nothing),
#   * a filename merely CONTAINING `.DS_Store` is not matched.
#
# Run with: bash check-junk-files/tests/test-check-junk-files.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
check_script="$script_dir/../check-junk-files.sh"
action_yml="$script_dir/../action.yml"
workflow_yml="$script_dir/../../.github/workflows/check-junk-files.yml"

DEFAULT_PATTERNS='.DS_Store, ._*, .Rproj.user, .Rhistory, .RData, .httr-oauth, .quarto, Thumbs.db, desktop.ini'

failures=0
case_name=""
work_dir=""
repo_dir=""
stdout_file=""
summary_file=""
run_status=0

fail() {
  echo "  FAIL [$case_name]: $*" >&2
  failures=$((failures + 1))
}

assert_status() {
  if [ "$run_status" != "$1" ]; then
    fail "expected exit status $1, got $run_status"
    sed -n '1,20p' "$stdout_file" >&2
  fi
}

assert_stdout_contains() {
  grep -qF -- "$1" "$stdout_file" || fail "expected on stdout: $1"
}

assert_stdout_not_contains() {
  grep -qF -- "$1" "$stdout_file" && fail "expected NOT on stdout: $1"
  return 0
}

assert_summary_contains() {
  grep -qF -- "$1" "$summary_file" || fail "expected in the step summary: $1"
}

# Build a throwaway repo. Every path in "$@" is created and force-added, so a
# junk file lands in the index even when the machine running these tests has a
# vaccinated global gitignore of its own -- without -f, `git add` on a
# developer laptop silently skips the very files under test.
new_case() {
  case_name="$1"
  shift
  work_dir="$(mktemp -d)"
  repo_dir="$work_dir/repo"
  stdout_file="$work_dir/stdout.txt"
  summary_file="$work_dir/summary.md"
  : > "$summary_file"
  mkdir -p "$repo_dir"
  git -C "$repo_dir" init -q .
  local path
  for path in "$@"; do
    mkdir -p "$repo_dir/$(dirname "$path")"
    printf 'content\n' > "$repo_dir/$path"
  done
  git -C "$repo_dir" add -Af . >/dev/null 2>&1
  # A bare `tests` rather than an address: git accepts any string here, and
  # an email-shaped one trips the repo's own check-phi selftest job, which
  # scans added lines across the tree.
  git -C "$repo_dir" -c user.email=tests -c user.name=tests \
    commit -qm "fixture" >/dev/null 2>&1
}

# Run the script against the current case's repo. Any KEY=VALUE arguments are
# exported for that run only.
run_check() {
  local -a env_args=("JUNK_TARGET=$repo_dir" "GITHUB_STEP_SUMMARY=$summary_file"
    "RUNNER_TEMP=$work_dir" "JUNK_PATTERNS=$DEFAULT_PATTERNS")
  env_args+=("$@")
  env "${env_args[@]}" bash "$check_script" > "$stdout_file" 2>&1
  run_status=$?
}

cleanup_case() {
  [ -n "$work_dir" ] && rm -rf "$work_dir"
}

echo "check-junk-files tests"

# --- A clean tree passes, and says what it examined -------------------------
# "0 matches" alone cannot be told apart from a scan that ran against nothing,
# so the examined count is asserted rather than only the verdict.
new_case "clean tree" "README.md" "R/analysis.R"
run_check
assert_status 0
assert_stdout_contains "No junk files are tracked."
assert_stdout_contains "2 tracked file(s) examined against 9 pattern(s); 0 match(es)."
cleanup_case

# --- A tracked .DS_Store fails, names the file, and gives the fix ------------
new_case "root .DS_Store" ".DS_Store" "README.md"
run_check
assert_status 1
assert_stdout_contains "::error file=.DS_Store::"
assert_summary_contains "git rm --cached '.DS_Store'"
assert_summary_contains "usethis::git_vaccinate()"
assert_summary_contains "core.excludesFile"
cleanup_case

# --- gitignore patterns match at any depth ----------------------------------
new_case "nested junk" "a/b/c/.DS_Store" "a/.Rhistory" "a/b/._sidecar.R" "README.md"
run_check
assert_status 1
assert_stdout_contains "::error file=a/b/c/.DS_Store::"
assert_stdout_contains "::error file=a/.Rhistory::"
assert_stdout_contains "::error file=a/b/._sidecar.R::"
cleanup_case

# --- .RData, not .Rdata -----------------------------------------------------
# gitignore matching is case-sensitive on the Linux runners these actions run
# on, and the file R actually writes is `.RData`. usethis's own
# `git_ignore_lines` spells it that way too (r-lib/usethis, R/git.R).
new_case "RData capitalization" ".RData" "README.md"
run_check
assert_status 1
assert_stdout_contains "::error file=.RData::"
cleanup_case

# --- NEGATIVE: a name merely CONTAINING a pattern is not a match ------------
new_case "substring is not a match" "docs/img.DS_Store" "notes-Thumbs.db.md" "README.md"
run_check
assert_status 0
assert_stdout_contains "0 match(es)"
cleanup_case

# --- NEGATIVE: an untracked junk file is not reported -----------------------
# The scan reads the index. A `.DS_Store` sitting in a working tree that was
# never committed is not this check's business, and reporting it would fail
# every PR on a macOS contributor's machine.
new_case "untracked junk" "README.md"
printf 'x\n' > "$repo_dir/.DS_Store"
run_check
assert_status 0
assert_stdout_contains "0 match(es)"
cleanup_case

# --- NEGATIVE: standard excludes are not consulted --------------------------
# Killer case. `git ls-files -i` reports a force-added file matching the repo's
# own .gitignore as soon as --exclude-standard is passed. Whether to keep a
# force-added file is the caller's decision, not this check's, so the flag is
# deliberately omitted -- and adding it turns this red.
new_case "force-added file in .gitignore" ".gitignore" "build.log" "README.md"
printf 'build.log\n' > "$repo_dir/.gitignore"
git -C "$repo_dir" add -f .gitignore build.log >/dev/null 2>&1
git -C "$repo_dir" -c user.email=tests -c user.name=tests \
  commit -qm "ignore build.log" >/dev/null 2>&1
run_check
assert_status 0
assert_stdout_not_contains "build.log"
cleanup_case

# --- NEGATIVE: paths-ignore really exempts a directory ----------------------
# Killer case. Implemented as gitignore `!` lines instead of git pathspec
# exclusions, `vendor/` re-includes nothing and this file is still reported --
# a suppression that fails silently, in the noisy direction.
new_case "paths-ignore directory" "vendor/.DS_Store" "src/.DS_Store" "README.md"
run_check "JUNK_PATHS_IGNORE=vendor/"
assert_status 1
assert_stdout_contains "::error file=src/.DS_Store::"
assert_stdout_not_contains "vendor/.DS_Store"
cleanup_case

# --- paths-ignore can exempt every match, leaving a pass --------------------
new_case "paths-ignore everything" "vendor/.DS_Store" "README.md"
run_check "JUNK_PATHS_IGNORE=vendor/"
assert_status 0
assert_stdout_contains "0 match(es)"
cleanup_case

# --- NEGATIVE: an empty pattern set is an error, not a pass -----------------
# Killer case. `git ls-files -i -X <empty>` exits 0 with no output, so dropping
# this guard yields a green check that examined no patterns at all.
new_case "empty patterns" ".DS_Store" "README.md"
run_check "JUNK_PATTERNS="
assert_status 1
assert_stdout_contains "patterns input is empty after parsing"
cleanup_case

new_case "patterns that are only comments" ".DS_Store" "README.md"
run_check "JUNK_PATTERNS=# nothing here
   "
assert_status 1
assert_stdout_contains "patterns input is empty after parsing"
cleanup_case

# --- Comments and blank lines are stripped, not treated as patterns ---------
new_case "comments in patterns" ".DS_Store" "README.md"
run_check "JUNK_PATTERNS=# junk we care about
.DS_Store

  .Rhistory  # trailing comment
"
assert_status 1
assert_stdout_contains "against 2 pattern(s)"
assert_stdout_contains "::error file=.DS_Store::"
cleanup_case

# --- fail: false warns without blocking -------------------------------------
new_case "fail false" ".DS_Store" "README.md"
run_check "JUNK_FAIL=false"
assert_status 0
assert_stdout_contains "::warning file=.DS_Store::"
assert_stdout_not_contains "::error"
cleanup_case

# --- fail normalization is fail-CLOSED --------------------------------------
# Only an explicit "false" opts out. `'False'` and a padded `' false '` are the
# same opt-out; anything else, including `'yes'`, still blocks. A gate that
# silently downgraded on a typo would report green over a real finding.
for value in "False" " false " "FALSE"; do
  new_case "fail normalization opts out on '$value'" ".DS_Store" "README.md"
  run_check "JUNK_FAIL=$value"
  assert_status 0
  cleanup_case
done
for value in "yes" "0" "no" "" "true"; do
  new_case "fail normalization still blocks on '$value'" ".DS_Store" "README.md"
  run_check "JUNK_FAIL=$value"
  assert_status 1
  cleanup_case
done

# --- A path with a space survives the NUL-separated read --------------------
new_case "path with a space" "my folder/.DS_Store" "README.md"
run_check
assert_status 1
assert_stdout_contains "::error file=my folder/.DS_Store::"
assert_summary_contains "git rm --cached 'my folder/.DS_Store'"
cleanup_case

# --- A non-git target is an error rather than a vacuous pass ----------------
new_case "not a git repository" "README.md"
rm -rf "$repo_dir/.git"
run_check
assert_status 1
assert_stdout_contains "is not a git repository"
cleanup_case

# --- The two declared defaults agree ----------------------------------------
# `patterns` is declared three times: once in the script's own test constant
# above, once in action.yml, and once in the reusable workflow. The gha#303
# precedent applies -- assert the agreement rather than leaving it to a
# comment, since a drift here means a consumer of the reusable workflow gets a
# different pattern set from a consumer of the composite, with nothing red.
case_name="declared defaults agree"
stdout_file="$(mktemp)"
work_dir="$(dirname "$stdout_file")"
for f in "$action_yml" "$workflow_yml"; do
  declared="$(grep -m1 "^ *default: '\.DS_Store," "$f" | sed -e "s/^ *default: '//" -e "s/'$//")"
  if [ "$declared" != "$DEFAULT_PATTERNS" ]; then
    fail "$f declares patterns default:
  $declared
expected:
  $DEFAULT_PATTERNS"
  fi
done
rm -f "$stdout_file"

if [ "$failures" -ne 0 ]; then
  echo "$failures assertion(s) failed." >&2
  exit 1
fi

echo "All check-junk-files tests passed."
