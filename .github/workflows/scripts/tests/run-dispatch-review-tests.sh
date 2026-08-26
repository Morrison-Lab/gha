#!/usr/bin/env bash
# Exercises dispatch-review.sh offline (gha#419).
# Usage: bash .github/workflows/scripts/tests/run-dispatch-review-tests.sh

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../../" && pwd)"
dispatch_script="$repo_root/.github/workflows/scripts/dispatch-review.sh"

failures=0

# Test 1: Same-repo PR with PR_BRANCH includes --ref
out="$(PR_NUMBER="123" PR_BRANCH="feature-x" PR_HEAD_REPO="Morrison-Lab/gha" GH_REPO="Morrison-Lab/gha" PR_CHANGED_FILES="README.md" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'gh workflow run claude-code-review.yml --ref feature-x -f pr_number=123'; then
  echo "OK   dispatch-review.sh includes --ref for same-repo PR"
else
  echo "::error::dispatch-review.sh failed to include --ref for same-repo PR; got: $out"
  failures=$((failures + 1))
fi

# Test 2: Fork PR omits --ref and prints fork notice
out="$(PR_NUMBER="124" PR_BRANCH="feature-fork" PR_HEAD_REPO="external-user/gha" GH_REPO="Morrison-Lab/gha" PR_CHANGED_FILES="README.md" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'is from a fork' && echo "$out" | grep -q 'gh workflow run claude-code-review.yml  -f pr_number=124'; then
  echo "OK   dispatch-review.sh omits --ref for fork PR"
else
  echo "::error::dispatch-review.sh failed to omit --ref for fork PR; got: $out"
  failures=$((failures + 1))
fi

# Test 3: Empty PR_BRANCH with mock gh api resolving branch via API
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cat <<'EOF' > "$tmp_dir/gh"
#!/usr/bin/env bash
if [[ "$1" == "api" ]]; then
  echo '{"branch":"api-branch","head_repo":"Morrison-Lab/gha"}'
  exit 0
fi
echo "Unexpected gh invocation: $@" >&2
exit 1
EOF
chmod +x "$tmp_dir/gh"

if ! command -v jq >/dev/null 2>&1; then
  cat <<'EOF' > "$tmp_dir/jq"
#!/usr/bin/env bash
python3 -c "import sys, json; data=json.loads(sys.stdin.read()); field=sys.argv[2].lstrip('.').split(' ')[0]; print(data.get(field) or '')" "$@"
EOF
  chmod +x "$tmp_dir/jq"
fi

out="$(PATH="$tmp_dir:$PATH" PR_NUMBER="125" PR_BRANCH="" PR_HEAD_REPO="" GH_REPO="Morrison-Lab/gha" PR_CHANGED_FILES="README.md" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'attempting API lookup for PR #125' && echo "$out" | grep -q 'gh workflow run claude-code-review.yml --ref api-branch -f pr_number=125'; then
  echo "OK   dispatch-review.sh resolves empty PR_BRANCH via API lookup"
else
  echo "::error::dispatch-review.sh failed API branch resolution; got: $out"
  failures=$((failures + 1))
fi

# Test 4: Unresolvable PR_BRANCH prints notice and omits --ref
cat <<'EOF' > "$tmp_dir/gh"
#!/usr/bin/env bash
if [[ "$1" == "api" ]]; then
  exit 1
fi
echo "Unexpected gh invocation: $@" >&2
exit 1
EOF

out="$(PATH="$tmp_dir:$PATH" PR_NUMBER="126" PR_BRANCH="" PR_HEAD_REPO="" GH_REPO="Morrison-Lab/gha" PR_CHANGED_FILES="README.md" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'PR_BRANCH could not be resolved' && echo "$out" | grep -q 'gh workflow run claude-code-review.yml -f pr_number=126'; then
  echo "OK   dispatch-review.sh handles unresolvable PR_BRANCH gracefully"
else
  echo "::error::dispatch-review.sh failed unresolvable PR_BRANCH test; got: $out"
  failures=$((failures + 1))
fi

# Test 5: Custom review workflow and context notice
out="$(PR_NUMBER="127" PR_BRANCH="main" PR_HEAD_REPO="Morrison-Lab/gha" GH_REPO="Morrison-Lab/gha" REVIEW_WF="custom-review.yml" CONTEXT_NOTICE="for late request" PR_CHANGED_FILES="README.md" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'gh workflow run custom-review.yml --ref main -f pr_number=127'; then
  echo "OK   dispatch-review.sh accepts custom review workflow"
else
  echo "::error::dispatch-review.sh failed custom review workflow test; got: $out"
  failures=$((failures + 1))
fi

# Test 6: Missing PR_NUMBER exits non-zero
if GH_REPO="Morrison-Lab/gha" bash "$dispatch_script" >/dev/null 2>&1; then
  echo "::error::dispatch-review.sh should fail when PR_NUMBER is missing"
  failures=$((failures + 1))
else
  echo "OK   dispatch-review.sh fails when PR_NUMBER is missing"
fi

# Test 7: Empty PR_HEAD_REPO conservatively omits --ref (fork-like fallback)
cat <<'EOF' > "$tmp_dir/gh"
#!/usr/bin/env bash
if [[ "$1" == "api" ]]; then
  echo '{"branch":"api-branch","head_repo":""}'
  exit 0
fi
echo "Unexpected gh invocation: $@" >&2
exit 1
EOF

out="$(PATH="$tmp_dir:$PATH" PR_NUMBER="128" PR_BRANCH="" PR_HEAD_REPO="" GH_REPO="Morrison-Lab/gha" PR_CHANGED_FILES="README.md" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'is from a fork' && echo "$out" | grep -q 'gh workflow run claude-code-review.yml  -f pr_number=128'; then
  echo "OK   dispatch-review.sh conservatively omits --ref when PR_HEAD_REPO is empty"
else
  echo "::error::dispatch-review.sh failed empty PR_HEAD_REPO fallback test; got: $out"
  failures=$((failures + 1))
fi

# Test 8: A PR that edits top-level workflow YAML omits --ref even on a
# same-repo branch, so GitHub executes the default-branch caller (gha#598).
out="$(PR_NUMBER="129" PR_BRANCH="feature-wf" PR_HEAD_REPO="Morrison-Lab/gha" GH_REPO="Morrison-Lab/gha" PR_CHANGED_FILES=".github/workflows/_selftest.yml" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'edits workflow files' && echo "$out" | grep -q 'gh workflow run claude-code-review.yml  -f pr_number=129' && ! echo "$out" | grep -q -- '--ref feature-wf'; then
  echo "OK   dispatch-review.sh omits --ref when the PR edits workflow YAML"
else
  echo "::error::dispatch-review.sh failed to omit --ref for a workflow-editing PR; got: $out"
  failures=$((failures + 1))
fi

# Test 9: Nested scripts under .github/workflows/ are not workflow YAML, so
# --ref is kept. Without this, dropping the nested-path guard would still
# pass test 8.
out="$(PR_NUMBER="130" PR_BRANCH="feature-scripts" PR_HEAD_REPO="Morrison-Lab/gha" GH_REPO="Morrison-Lab/gha" PR_CHANGED_FILES=".github/workflows/scripts/foo.sh" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'gh workflow run claude-code-review.yml --ref feature-scripts -f pr_number=130'; then
  echo "OK   dispatch-review.sh keeps --ref when only workflow scripts change"
else
  echo "::error::dispatch-review.sh omitted --ref for a scripts-only change; got: $out"
  failures=$((failures + 1))
fi

# Test 10: A failed files-list API call omits --ref rather than dispatching
# at an unknown PR head (gha#598). PR_CHANGED_FILES is unset so the live
# lookup runs; the mock gh fails.
cat <<'EOF' > "$tmp_dir/gh"
#!/usr/bin/env bash
echo "Unexpected gh invocation: $@" >&2
exit 1
EOF
out="$(PATH="$tmp_dir:$PATH" PR_NUMBER="131" PR_BRANCH="feature-api-fail" PR_HEAD_REPO="Morrison-Lab/gha" GH_REPO="Morrison-Lab/gha" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'Could not list a complete file set' && echo "$out" | grep -q 'gh workflow run claude-code-review.yml  -f pr_number=131' && ! echo "$out" | grep -q -- '--ref feature-api-fail'; then
  echo "OK   dispatch-review.sh omits --ref when the files API fails"
else
  echo "::error::dispatch-review.sh did not omit --ref on files-API failure; got: $out"
  failures=$((failures + 1))
fi

# Test 11: A successful but truncated files list (listed < changed_files)
# omits --ref. GitHub's endpoint caps at 3000 files and still returns 200,
# so treating that 200 as complete would dispatch --ref at an unknown tree.
# The notice must not be the "edits workflow files" one: truncation is not
# a detected workflow edit.
cat <<'EOF' > "$tmp_dir/gh"
#!/usr/bin/env bash
for arg in "$@"; do
  case "$arg" in
    */files*)
      printf 'README.md\nCLAUDE.md\n'
      exit 0
      ;;
    */pulls/*)
      echo '{"changed_files":5}'
      exit 0
      ;;
  esac
done
echo "Unexpected gh invocation: $@" >&2
exit 1
EOF
out="$(PATH="$tmp_dir:$PATH" PR_NUMBER="132" PR_BRANCH="feature-truncated" PR_HEAD_REPO="Morrison-Lab/gha" GH_REPO="Morrison-Lab/gha" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'Could not list a complete file set' && echo "$out" | grep -q 'gh workflow run claude-code-review.yml  -f pr_number=132' && ! echo "$out" | grep -q -- '--ref feature-truncated' && ! echo "$out" | grep -q 'edits workflow files'; then
  echo "OK   dispatch-review.sh omits --ref when the files list is truncated"
else
  echo "::error::dispatch-review.sh did not omit --ref on a truncated files list; got: $out"
  failures=$((failures + 1))
fi

# Test 12: A complete non-workflow list keeps --ref. Without this, a
# comparison that always failed would pass test 11 and still look like a
# fix.
cat <<'EOF' > "$tmp_dir/gh"
#!/usr/bin/env bash
for arg in "$@"; do
  case "$arg" in
    */files*)
      printf 'README.md\nCLAUDE.md\n'
      exit 0
      ;;
    */pulls/*)
      echo '{"changed_files":2}'
      exit 0
      ;;
  esac
done
echo "Unexpected gh invocation: $@" >&2
exit 1
EOF
out="$(PATH="$tmp_dir:$PATH" PR_NUMBER="133" PR_BRANCH="feature-complete" PR_HEAD_REPO="Morrison-Lab/gha" GH_REPO="Morrison-Lab/gha" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'gh workflow run claude-code-review.yml --ref feature-complete -f pr_number=133'; then
  echo "OK   dispatch-review.sh keeps --ref when the files list is complete"
else
  echo "::error::dispatch-review.sh omitted --ref for a complete non-workflow list; got: $out"
  failures=$((failures + 1))
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures dispatch-review test case(s) failed"
  exit 1
fi

echo "All dispatch-review test cases passed."
