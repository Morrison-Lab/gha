#!/usr/bin/env bash
# Asserts matching behavior for the inline workflow-edit guard under
# pipefail and with CRLF input (gha#915).
#
# Usage: bash .github/workflows/scripts/tests/run-workflow-edit-guard-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"

matches_workflow_edits() {
  local files="$1"
  files=$(printf '%s' "$files" | tr -d '\r')
  if grep -qE '^\.github/workflows/[^/]+\.ya?ml$' <<< "$files"; then
    return 0
  fi
  return 1
}

failures=0
checked=0

check() {
  local label="$1"
  local expected="$2"
  local files="$3"
  local actual="false"
  if matches_workflow_edits "$files"; then
    actual="true"
  fi
  checked=$((checked + 1))
  if [[ "$actual" != "$expected" ]]; then
    echo "FAIL: $label (want $expected, got $actual)" >&2
    failures=$((failures + 1))
  else
    echo "OK   $label"
  fi
}

# Matching cases
check "top-level yml workflow" "true" ".github/workflows/foo.yml"
check "top-level yaml workflow" "true" ".github/workflows/bar.yaml"
check "selftest workflow" "true" ".github/workflows/_selftest.yml"
check "multiple files including workflow" "true" $'README.md\n.github/workflows/review.yml\nsrc/index.js'
check "CRLF file list" "true" $'.github/workflows/test.yml\r\nREADME.md\r\n'
check "CRLF lone workflow" "true" $'.github/workflows/test.yml\r'

# Non-matching cases
check "empty input" "false" ""
check "non-workflow file" "false" "README.md"
check "nested script under workflows" "false" ".github/workflows/scripts/test.sh"
check "nested yaml under scripts" "false" ".github/workflows/scripts/foo.yml"
check "composite action yml" "false" ".github/actions/run-review/action.yml"
check "yaml outside workflows" "false" "docs/guide.yml"
check "filename containing workflows" "false" "my-workflows.yml"

# Pipefail regression test for gha#915:
# Under set -o pipefail, the old `printf '%s\n' "$files" | grep -qE ...` fails open
# when grep exits after matching line 1 and printf dies of SIGPIPE on large input.
# A here-string must succeed 20/20 trials on large inputs (>100k bytes).
echo "Running pipefail large-input trials (gha#915)..."
large_files=".github/workflows/match.yml"$'\n'
for i in $(seq 1 3500); do
  large_files+="some/deeply/nested/non/workflow/path/to/fill/pipe/buffer/file_${i}.txt"$'\n'
done

byte_count=$(printf '%s' "$large_files" | wc -c)
echo "  Payload size: $byte_count bytes"

pipefail_trials=20
pipefail_fails=0
for trial in $(seq 1 "$pipefail_trials"); do
  if ! matches_workflow_edits "$large_files"; then
    pipefail_fails=$((pipefail_fails + 1))
  fi
done

checked=$((checked + 1))
if [[ "$pipefail_fails" -gt 0 ]]; then
  echo "FAIL: pipefail large-input trials ($pipefail_fails/$pipefail_trials failed)" >&2
  failures=$((failures + 1))
else
  echo "OK   pipefail large-input trials ($pipefail_trials/$pipefail_trials passed, 0 failures)"
fi

# Static assertion against the deployed files in .github/workflows and examples:
# Asserts that no file in the repository uses the vulnerable piped-grep pattern,
# and that all 6 expected call sites in the 5 files implement the safe here-string
# guard with CR-stripping.
echo "Checking repository workflow files and example templates..."

vulnerable_piped_greps=$(grep -rnE "printf.*\|[[:space:]]*grep -q.*github/workflows" "$repo_root/.github/workflows" "$repo_root/examples" || true)
checked=$((checked + 1))
if [ -n "$vulnerable_piped_greps" ]; then
  echo "FAIL: Found vulnerable piped grep pattern in workflow files:" >&2
  echo "$vulnerable_piped_greps" >&2
  failures=$((failures + 1))
else
  echo "OK   no vulnerable piped workflow greps in .github/workflows/ or examples/"
fi

target_files=(
  "$repo_root/.github/workflows/claude-review.yml"
  "$repo_root/.github/workflows/claude.yml"
  "$repo_root/.github/workflows/gemini.yml"
  "$repo_root/examples/antigravity-code-review.yml"
  "$repo_root/examples/claude-code-review.yml"
)

expected_guard='grep -qE '\''^\.github/workflows/[^/]+\.ya?ml$'\'' <<< "$files"'
expected_strip='files=$(printf '\''%s'\'' "$files" | tr -d '\''\r'\'')'

for target in "${target_files[@]}"; do
  rel_path="${target#$repo_root/}"
  checked=$((checked + 1))
  if ! grep -Fq "$expected_guard" "$target"; then
    echo "FAIL: $rel_path missing required here-string workflow guard" >&2
    failures=$((failures + 1))
  elif ! grep -Fq "$expected_strip" "$target"; then
    echo "FAIL: $rel_path missing required CR stripping before workflow guard" >&2
    failures=$((failures + 1))
  else
    echo "OK   $rel_path contains safe here-string guard and CR-stripping"
  fi
done

gemini_count=$(grep -Fc "$expected_guard" "$repo_root/.github/workflows/gemini.yml" || true)
checked=$((checked + 1))
if [ "$gemini_count" -ne 2 ]; then
  echo "FAIL: gemini.yml expected 2 here-string sites, found $gemini_count" >&2
  failures=$((failures + 1))
else
  echo "OK   gemini.yml contains both here-string dispatch guard sites"
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures/$checked workflow-edit guard test(s) failed." >&2
  exit 1
fi

echo "All $checked workflow-edit guard tests passed."
