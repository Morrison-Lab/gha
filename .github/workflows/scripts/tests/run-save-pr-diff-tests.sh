#!/usr/bin/env bash
# Offline unit tests for save-pr-diff.sh.
# Covers the four shapes:
#   1. success (non-empty diff written, output path set)
#   2. empty output (gh succeeds with 0 bytes -> file removed, path empty)
#   3. command failure (gh fails non-zero -> file removed, path empty)
#   4. partial failure (gh writes bytes then fails -> file removed, path empty)
# Mutation tests:
#   5. removing rm -f causes partial failure test to fail
#   6. removing -s emptiness check causes empty output test to fail
set -euo pipefail

PASS=0
FAIL=0

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/save-pr-diff.sh"

run_case() {
  local label="$1"
  local stub_mode="$2"
  local expect_file="$3" # "present" or "absent"
  local expect_path_nonempty="$4" # "true" or "false"

  local case_dir="$tmpdir/case_${label// /_}"
  mkdir -p "$case_dir/bin" "$case_dir/ws"
  local out_file="$case_dir/github_output"
  touch "$out_file"

  # Write stub gh
  cat <<STUB > "$case_dir/bin/gh"
#!/usr/bin/env bash
if [ "\$1" = "pr" ] && [ "\$2" = "diff" ]; then
  case "$stub_mode" in
    success)
      echo "diff --git a/foo b/foo"
      echo "--- a/foo"
      echo "+++ b/foo"
      echo "@@ -1 +1 @@"
      echo "-old"
      echo "+new"
      exit 0
      ;;
    empty)
      exit 0
      ;;
    failure)
      echo "error: failed to fetch diff" >&2
      exit 1
      ;;
    partial_failure)
      echo "diff --git a/foo b/foo"
      echo "--- a/foo"
      echo "incomplete diff line"
      exit 1
      ;;
  esac
fi
exit 1
STUB
  chmod +x "$case_dir/bin/gh"

  local target="$case_dir/ws/.claude-review-pr.diff"
  (
    export PATH="$case_dir/bin:$PATH"
    export GITHUB_WORKSPACE="$case_dir/ws"
    export GITHUB_OUTPUT="$out_file"
    export PR_NUMBER="42"
    export REPO="owner/repo"
    export TARGET_PATH="$target"
    bash "$SCRIPT_PATH"
  )

  local path_val
  path_val="$(sed -n 's/^path=//p' "$out_file" || true)"

  local test_ok=true
  if [ "$expect_file" = "present" ]; then
    if [ ! -s "$target" ]; then
      echo "FAIL: $label (expected file to be present and non-empty)"
      test_ok=false
    fi
  else
    if [ -f "$target" ]; then
      echo "FAIL: $label (expected file to be absent)"
      test_ok=false
    fi
  fi

  if [ "$expect_path_nonempty" = "true" ]; then
    if [ -z "$path_val" ]; then
      echo "FAIL: $label (expected non-empty path in GITHUB_OUTPUT)"
      test_ok=false
    fi
  else
    if [ -n "$path_val" ]; then
      echo "FAIL: $label (expected empty path in GITHUB_OUTPUT, got '$path_val')"
      test_ok=false
    fi
  fi

  if [ "$test_ok" = "true" ]; then
    echo "OK: $label"
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
  fi
}

echo "Running save-pr-diff unit tests..."
run_case "successful diff save" "success" "present" "true"
run_case "empty diff output" "empty" "absent" "false"
run_case "gh diff failure" "failure" "absent" "false"
run_case "partial bytes then failure" "partial_failure" "absent" "false"

echo "save-pr-diff: examined $((PASS + FAIL)) cases, $FAIL failed."
if [ "$FAIL" -ne 0 ]; then
  exit 1
fi
