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
python3 -c "import sys, json; data=json.loads(sys.stdin.read()); expr=sys.argv[2] if len(sys.argv) > 2 else ''; fields=[f.strip().lstrip('.') for f in expr.split('//') if f.strip() and f.strip() != 'empty']; val = next((data.get(f) for f in fields if data.get(f)), ''); print(val)" "$@"
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

# Test 8: A PR that edits top-level workflow YAML skips review dispatch
# rather than dispatching from the default branch, which would preempt
# in-flight PR-head reviews and attach check-runs to the default branch (gha#921).
out="$(PR_NUMBER="129" PR_BRANCH="feature-wf" PR_HEAD_REPO="Morrison-Lab/gha" GH_REPO="Morrison-Lab/gha" PR_CHANGED_FILES=".github/workflows/_selftest.yml" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'edits workflow files' && echo "$out" | grep -q 'skipping review dispatch' && ! echo "$out" | grep -q 'gh workflow run'; then
  echo "OK   dispatch-review.sh skips review dispatch when the PR edits workflow YAML"
else
  echo "::error::dispatch-review.sh failed to skip review dispatch for a workflow-editing PR; got: $out"
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

# Test 10: A failed files-list API call skips review dispatch rather than
# dispatching at an unknown PR head or from the default branch (gha#598, gha#921).
# PR_CHANGED_FILES is unset so the live lookup runs; the mock gh fails.
cat <<'EOF' > "$tmp_dir/gh"
#!/usr/bin/env bash
echo "Unexpected gh invocation: $@" >&2
exit 1
EOF
out="$(PATH="$tmp_dir:$PATH" PR_NUMBER="131" PR_BRANCH="feature-api-fail" PR_HEAD_REPO="Morrison-Lab/gha" GH_REPO="Morrison-Lab/gha" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'Could not list a complete file set' && echo "$out" | grep -q 'skipping review dispatch' && ! echo "$out" | grep -q 'gh workflow run'; then
  echo "OK   dispatch-review.sh skips dispatch when the files API fails"
else
  echo "::error::dispatch-review.sh did not skip dispatch on files-API failure; got: $out"
  failures=$((failures + 1))
fi

# Test 11: A successful but truncated files list (listed < changed_files)
# skips review dispatch. GitHub's endpoint caps at 3000 files and still returns 200,
# so treating that 200 as complete would risk executing untrusted workflow YAML
# or preempting PR-head checks (gha#598, gha#921).
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
if echo "$out" | grep -q 'Could not list a complete file set' && echo "$out" | grep -q 'skipping review dispatch' && ! echo "$out" | grep -q 'gh workflow run'; then
  echo "OK   dispatch-review.sh skips dispatch when the files list is truncated"
else
  echo "::error::dispatch-review.sh did not skip dispatch on a truncated files list; got: $out"
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

# Test 13: Fork PR with DEFAULT_BRANCH includes --ref with the default branch
out="$(PR_NUMBER="134" PR_BRANCH="feature-fork" PR_HEAD_REPO="external-user/gha" GH_REPO="Morrison-Lab/gha" DEFAULT_BRANCH="main" PR_CHANGED_FILES="README.md" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'is from a fork' && echo "$out" | grep -q 'gh workflow run claude-code-review.yml --ref main -f pr_number=134'; then
  echo "OK   dispatch-review.sh passes default branch --ref for fork PR when DEFAULT_BRANCH is set"
else
  echo "::error::dispatch-review.sh failed to pass default branch --ref for fork PR; got: $out"
  failures=$((failures + 1))
fi

# Test 14: Workflow-editing PR with DEFAULT_BRANCH skips dispatch (gha#921)
out="$(PR_NUMBER="135" PR_BRANCH="feature-wf" PR_HEAD_REPO="Morrison-Lab/gha" GH_REPO="Morrison-Lab/gha" DEFAULT_BRANCH="main" PR_CHANGED_FILES=".github/workflows/_selftest.yml" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'edits workflow files' && echo "$out" | grep -q 'skipping review dispatch' && ! echo "$out" | grep -q 'gh workflow run'; then
  echo "OK   dispatch-review.sh skips dispatch for workflow edits even when DEFAULT_BRANCH is set"
else
  echo "::error::dispatch-review.sh failed to skip dispatch for workflow edits with DEFAULT_BRANCH; got: $out"
  failures=$((failures + 1))
fi

# Test 15: Unresolvable PR_BRANCH with DEFAULT_BRANCH set passes --ref with the default branch
cat <<'EOF' > "$tmp_dir/gh"
#!/usr/bin/env bash
if [[ "$1" == "api" ]]; then
  exit 1
fi
echo "Unexpected gh invocation: $@" >&2
exit 1
EOF
out="$(PATH="$tmp_dir:$PATH" PR_NUMBER="136" PR_BRANCH="" PR_HEAD_REPO="" GH_REPO="Morrison-Lab/gha" DEFAULT_BRANCH="main" PR_CHANGED_FILES="README.md" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'PR_BRANCH could not be resolved' && echo "$out" | grep -q 'gh workflow run claude-code-review.yml --ref main -f pr_number=136'; then
  echo "OK   dispatch-review.sh passes default branch --ref when PR_BRANCH is unresolvable and DEFAULT_BRANCH is set"
else
  echo "::error::dispatch-review.sh failed unresolvable PR_BRANCH with DEFAULT_BRANCH test; got: $out"
  failures=$((failures + 1))
fi

# Test 16: Incomplete file set with DEFAULT_BRANCH set skips dispatch (gha#921)
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
out="$(PATH="$tmp_dir:$PATH" PR_NUMBER="137" PR_BRANCH="feature-truncated" PR_HEAD_REPO="Morrison-Lab/gha" GH_REPO="Morrison-Lab/gha" DEFAULT_BRANCH="main" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'Could not list a complete file set' && echo "$out" | grep -q 'skipping review dispatch' && ! echo "$out" | grep -q 'gh workflow run'; then
  echo "OK   dispatch-review.sh skips dispatch when files list is truncated even when DEFAULT_BRANCH is set"
else
  echo "::error::dispatch-review.sh failed truncated files list with DEFAULT_BRANCH test; got: $out"
  failures=$((failures + 1))
fi

# Test 17: Closed/merged PR with --is-closed true skips dispatch
out="$(PR_NUMBER="138" PR_BRANCH="feature-closed" PR_HEAD_REPO="Morrison-Lab/gha" GH_REPO="Morrison-Lab/gha" IS_CLOSED="true" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'PR #138 is closed or merged; skipping review dispatch' && ! echo "$out" | grep -q 'gh workflow run'; then
  echo "OK   dispatch-review.sh skips dispatch when IS_CLOSED is true"
else
  echo "::error::dispatch-review.sh failed to skip dispatch when IS_CLOSED is true; got: $out"
  failures=$((failures + 1))
fi

# Test 18: Empty PR_BRANCH where API returns closed PR skips dispatch
cat <<'EOF' > "$tmp_dir/gh"
#!/usr/bin/env bash
if [[ "$1" == "api" ]]; then
  echo '{"branch":"api-branch","head_repo":"Morrison-Lab/gha","state":"closed","merged":false}'
  exit 0
fi
echo "Unexpected gh invocation: $@" >&2
exit 1
EOF
out="$(PATH="$tmp_dir:$PATH" PR_NUMBER="139" PR_BRANCH="" PR_HEAD_REPO="" GH_REPO="Morrison-Lab/gha" DRY_RUN="true" bash "$dispatch_script")"
if echo "$out" | grep -q 'PR #139 is closed or merged; skipping review dispatch' && ! echo "$out" | grep -q 'gh workflow run'; then
  echo "OK   dispatch-review.sh skips dispatch when resolve-pr-info discovers closed PR"
else
  echo "::error::dispatch-review.sh failed to skip dispatch on closed PR from API; got: $out"
  failures=$((failures + 1))
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures dispatch-review test case(s) failed"
  exit 1
fi

echo "All dispatch-review test cases passed."
