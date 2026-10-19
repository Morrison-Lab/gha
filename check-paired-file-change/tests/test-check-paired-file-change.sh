#!/usr/bin/env bash
#
# Offline tests for check-paired-file-change/check-paired-file-change.sh.
#
# Drives the script against throwaway git repos built in $TMPDIR (nothing
# committed) and a stub `gh` on PFC_GH that prints canned labels, so the label
# logic runs with no network.
#
# The cases to keep if this is trimmed are the ones pinning a decision that is
# silent when reversed:
#   * an empty skip-label never exempts, and never calls the API,
#   * a failing label read fails the check (a swallowed error would read as
#     "no labels" and so as a failure that can never be waived, or worse, as
#     a pass if the logic were inverted),
#   * a skip label is matched case-insensitively against the live read,
#   * empty trigger-paths / required-paths are errors, not vacuous passes,
#   * a rename of a trigger file counts as a trigger change.
#
# Run with: bash check-paired-file-change/tests/test-check-paired-file-change.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
check_script="$script_dir/../check-paired-file-change.sh"
action_yml="$script_dir/../action.yml"
workflow_yml="$script_dir/../../.github/workflows/check-paired-file-change.yml"

failures=0
case_name=""
work_dir=""
repo_dir=""
stdout_file=""
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
  if grep -qF -- "$1" "$stdout_file"; then fail "expected NOT on stdout: $1"; fi
  return 0
}

begin_case() {
  case_name="$1"
  work_dir="$(mktemp -d)"
  repo_dir="$work_dir/repo"
  stdout_file="$work_dir/stdout.txt"
  mkdir -p "$repo_dir"
  git -C "$repo_dir" init -q -b main
  git -C "$repo_dir" config user.email "test@example.invalid"  # phi-allow
  git -C "$repo_dir" config user.name "Test"
  git -C "$repo_dir" config commit.gpgsign false
  echo base > "$repo_dir/macros.qmd"
  echo base > "$repo_dir/notation-choices.qmd"
  echo base > "$repo_dir/other.txt"
  git -C "$repo_dir" add -A
  git -C "$repo_dir" commit -q -m base
  git -C "$repo_dir" checkout -q -b feature
}

# Stub gh: prints $STUB_LABELS (one per line), exits $STUB_GH_STATUS, and
# records each call in $work_dir/gh-calls.
make_gh_stub() {
  cat > "$work_dir/gh" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "$(dirname "$0")/gh-calls"
printf '%s' "${STUB_LABELS:-}"
exit "${STUB_GH_STATUS:-0}"
STUB
  chmod +x "$work_dir/gh"
}

commit_change() {
  local f
  for f in "$@"; do
    echo "changed $RANDOM" >> "$repo_dir/$f"
  done
  git -C "$repo_dir" add -A
  git -C "$repo_dir" commit -q -m change
}

# run_check [VAR=value ...]: runs the script in the repo with defaults.
run_check() {
  (
    cd "$repo_dir" || exit 99
    env PFC_BASE_REF=main \
      PFC_TRIGGER_PATHS='macros.qmd' \
      PFC_REQUIRED_PATHS='notation-choices.qmd' \
      PFC_SKIP_LABEL='no-notation-change' \
      PFC_MESSAGE='Update notation-choices.qmd.' \
      PFC_PR_NUMBER=7 \
      GITHUB_REPOSITORY=o/r \
      PFC_GH="$work_dir/gh" \
      "$@" \
      bash "$check_script"
  ) > "$stdout_file" 2>&1
  run_status=$?
}

end_case() { rm -rf "$work_dir"; }

begin_case "trigger without required fails with the message"
make_gh_stub
commit_change macros.qmd
run_check
assert_status 1
assert_stdout_contains "::error title=Paired file change missing::Update notation-choices.qmd."
assert_stdout_contains "macros.qmd"
end_case

begin_case "trigger with required passes"
make_gh_stub
commit_change macros.qmd notation-choices.qmd
run_check
assert_status 0
[ ! -e "$work_dir/gh-calls" ] || fail "label API called although the pairing held"
end_case

begin_case "no trigger change passes"
make_gh_stub
commit_change other.txt
run_check
assert_status 0
assert_stdout_contains "nothing to pair"
end_case

begin_case "required alone passes"
make_gh_stub
commit_change notation-choices.qmd
run_check
assert_status 0
end_case

begin_case "live skip label exempts, case-insensitively"
make_gh_stub
commit_change macros.qmd
run_check STUB_LABELS=$'bug\nNo-Notation-Change\n'
assert_status 0
assert_stdout_contains "::notice::"
grep -qF "repos/o/r/issues/7/labels" "$work_dir/gh-calls" || fail "label read did not target the PR"
end_case

begin_case "an unrelated label does not exempt"
make_gh_stub
commit_change macros.qmd
run_check STUB_LABELS=$'bug\nno-notation-change-ish\n'
assert_status 1
end_case

begin_case "empty skip-label never exempts and never calls the API"
make_gh_stub
commit_change macros.qmd
run_check PFC_SKIP_LABEL= STUB_LABELS=$'\n'
assert_status 1
[ ! -e "$work_dir/gh-calls" ] || fail "label API called with an empty skip-label"
end_case

begin_case "a failing label read fails the check"
make_gh_stub
commit_change macros.qmd
run_check STUB_GH_STATUS=1 STUB_LABELS=no-notation-change
assert_status 1
assert_stdout_not_contains "::notice::"
end_case

begin_case "empty trigger-paths is an error"
make_gh_stub
commit_change macros.qmd
run_check PFC_TRIGGER_PATHS=' , '
assert_status 1
assert_stdout_contains "trigger-paths is empty"
end_case

begin_case "empty required-paths is an error"
make_gh_stub
commit_change macros.qmd
run_check PFC_REQUIRED_PATHS=
assert_status 1
assert_stdout_contains "required-paths is empty"
end_case

begin_case "empty base-ref skips"
make_gh_stub
commit_change macros.qmd
run_check PFC_BASE_REF=
assert_status 0
assert_stdout_contains "Skipping"
end_case

begin_case "multiple comma and newline separated pathspecs"
make_gh_stub
git -C "$repo_dir" checkout -q main
mkdir -p "$repo_dir/src"
echo x > "$repo_dir/src/a.R"
git -C "$repo_dir" add -A
git -C "$repo_dir" commit -q -m src
git -C "$repo_dir" checkout -q -B feature
commit_change src/a.R
run_check PFC_TRIGGER_PATHS=$'macros.qmd, src/*.R\n' PFC_REQUIRED_PATHS=$'docs/a.qmd\n notation-choices.qmd'
assert_status 1
assert_stdout_contains "src/a.R"
commit_change notation-choices.qmd
run_check PFC_TRIGGER_PATHS=$'macros.qmd, src/*.R\n' PFC_REQUIRED_PATHS=$'docs/a.qmd\n notation-choices.qmd'
assert_status 0
end_case

begin_case "renaming a trigger file is a trigger change"
make_gh_stub
git -C "$repo_dir" mv macros.qmd moved.qmd
git -C "$repo_dir" commit -q -m rename
run_check PFC_TRIGGER_PATHS='macros.qmd'
assert_status 1
end_case

begin_case "defaults agree between action.yml and the reusable workflow"
make_gh_stub
for key in skip-label message; do
  a="$(awk -v k="  $key:" '$0==k{f=1;next} f&&/^    default:/{sub(/^    default: /,"");print;exit} f&&/^  [a-z]/{exit}' "$action_yml")"
  w="$(awk -v k="      $key:" '$0==k{f=1;next} f&&/^        default:/{sub(/^        default: /,"");print;exit} f&&/^      [a-z]/{exit}' "$workflow_yml")"
  [ -n "$a" ] || fail "no default for $key in action.yml"
  [ "$a" = "$w" ] || fail "$key default differs: action.yml=[$a] workflow=[$w]"
done
end_case

if [ "$failures" -gt 0 ]; then
  echo "$failures failure(s)" >&2
  exit 1
fi
echo "All check-paired-file-change tests passed."
