#!/usr/bin/env bash
# Offline tests for list-pr-changed-files.sh (gha#598).
#
# The case that matters is the silent one: a successful files response
# shorter than changed_files must fail closed. Dropping that comparison
# turns the truncated-list case green and every other case still passes.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
list="$script_dir/../list-pr-changed-files.sh"

failures=0
checked=0

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

pass() {
  checked=$((checked + 1))
  echo "OK   $1"
}

fail() {
  checked=$((checked + 1))
  failures=$((failures + 1))
  echo "FAIL: $1"
  echo "  $2"
}

write_gh() {
  cat > "$tmp_dir/gh" <<'EOF'
#!/usr/bin/env bash
# Args after `api` are the path plus flags. Match /files before the PR
# path, because the files URL contains the PR URL as a prefix.
for arg in "$@"; do
  case "$arg" in
    */files*)
      if [ "${GH_FILES_FAIL:-0}" = "1" ]; then
        echo "files api failed" >&2
        exit 1
      fi
      printf '%s' "${GH_FILES_BODY:-}"
      exit 0
      ;;
  esac
done
for arg in "$@"; do
  case "$arg" in
    */pulls/*)
      if [ "${GH_PR_FAIL:-0}" = "1" ]; then
        echo "pr api failed" >&2
        exit 1
      fi
      printf '%s' "${GH_PR_BODY:-}"
      exit 0
      ;;
  esac
done
echo "Unexpected gh invocation: $*" >&2
exit 1
EOF
  chmod +x "$tmp_dir/gh"
}

write_gh

set +e
err_out="$(PR_NUMBER=1 bash "$list" 2>&1)"
err_code=$?
set -e
if [ "$err_code" -eq 1 ] && [[ "$err_out" == *"REPO and PR_NUMBER are required"* ]]; then
  pass "missing REPO fails closed"
else
  fail "missing REPO" "exit $err_code, $err_out"
fi

set +e
err_out="$(REPO=Morrison-Lab/gha bash "$list" 2>&1)"
err_code=$?
set -e
if [ "$err_code" -eq 1 ] && [[ "$err_out" == *"REPO and PR_NUMBER are required"* ]]; then
  pass "missing PR_NUMBER fails closed"
else
  fail "missing PR_NUMBER" "exit $err_code, $err_out"
fi

set +e
err_out="$(PATH="$tmp_dir:$PATH" GH_PR_FAIL=1 REPO=Morrison-Lab/gha PR_NUMBER=1 bash "$list" 2>&1)"
err_code=$?
set -e
if [ "$err_code" -eq 2 ] && [[ "$err_out" == *"could not read PR"* ]]; then
  pass "PR API failure fails closed"
else
  fail "PR API failure" "exit $err_code, $err_out"
fi

set +e
err_out="$(PATH="$tmp_dir:$PATH" GH_PR_BODY='{"changed_files":2}' GH_FILES_FAIL=1 REPO=Morrison-Lab/gha PR_NUMBER=1 bash "$list" 2>&1)"
err_code=$?
set -e
if [ "$err_code" -eq 2 ] && [[ "$err_out" == *"could not list files"* ]]; then
  pass "files API failure fails closed"
else
  fail "files API failure" "exit $err_code, $err_out"
fi

set +e
err_out="$(PATH="$tmp_dir:$PATH" GH_PR_BODY='{"changed_files":null}' GH_FILES_BODY=$'a.txt\n' REPO=Morrison-Lab/gha PR_NUMBER=1 bash "$list" 2>&1)"
err_code=$?
set -e
if [ "$err_code" -eq 2 ] && [[ "$err_out" == *"no usable changed_files"* ]]; then
  pass "null changed_files fails closed"
else
  fail "null changed_files" "exit $err_code, $err_out"
fi

set +e
err_out="$(PATH="$tmp_dir:$PATH" GH_PR_BODY='{"changed_files":"nope"}' GH_FILES_BODY=$'a.txt\n' REPO=Morrison-Lab/gha PR_NUMBER=1 bash "$list" 2>&1)"
err_code=$?
set -e
if [ "$err_code" -eq 2 ] && [[ "$err_out" == *"no usable changed_files"* ]]; then
  pass "non-numeric changed_files fails closed"
else
  fail "non-numeric changed_files" "exit $err_code, $err_out"
fi

set +e
out="$(PATH="$tmp_dir:$PATH" GH_PR_BODY='{"changed_files":2}' GH_FILES_BODY=$'README.md\nCLAUDE.md\n' REPO=Morrison-Lab/gha PR_NUMBER=1 bash "$list" 2>/dev/null)"
err_code=$?
set -e
if [ "$err_code" -eq 0 ] && [ "$out" = $'README.md\nCLAUDE.md' ]; then
  pass "complete two-file list succeeds"
else
  fail "complete two-file list" "exit $err_code, out=$(printf '%q' "$out")"
fi

set +e
err_out="$(PATH="$tmp_dir:$PATH" GH_PR_BODY='{"changed_files":5}' GH_FILES_BODY=$'README.md\nCLAUDE.md\n' REPO=Morrison-Lab/gha PR_NUMBER=1 bash "$list" 2>&1)"
err_code=$?
set -e
if [ "$err_code" -eq 2 ] && [[ "$err_out" == *"listed 2 of 5 files"* ]]; then
  pass "truncated list (listed < changed_files) fails closed"
else
  fail "truncated list" "exit $err_code, $err_out"
fi

set +e
out="$(PATH="$tmp_dir:$PATH" GH_PR_BODY='{"changed_files":0}' GH_FILES_BODY='' REPO=Morrison-Lab/gha PR_NUMBER=1 bash "$list" 2>/dev/null)"
err_code=$?
set -e
if [ "$err_code" -eq 0 ] && [ -z "$out" ]; then
  pass "empty complete list succeeds"
else
  fail "empty complete list" "exit $err_code, out=$(printf '%q' "$out")"
fi

if [ "$failures" -gt 0 ]; then
  echo "::error::$failures/$checked list-pr-changed-files test(s) failed"
  exit 1
fi
echo "All $checked list-pr-changed-files cases passed."
