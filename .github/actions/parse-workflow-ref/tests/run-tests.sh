#!/usr/bin/env bash
# Exercises parse-workflow-ref.sh against the shapes github.workflow_ref /
# github.job_workflow_ref can take: a tag ref, a branch ref, and a
# full-length commit SHA ref, each for a different repo/file than the
# others so a copy-paste mistake in the sed patterns doesn't go unnoticed.
# Wired into _selftest.yml's `review-fail-check` job (gha#191 review).
#
# Usage: bash .github/actions/parse-workflow-ref/tests/run-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
parse_script="$script_dir/../parse-workflow-ref.sh"

declare -A cases=(
  ["Morrison-Lab/gha/.github/workflows/claude-code-review.yml@v2"]="repo=Morrison-Lab/gha
path=.github/workflows/claude-code-review.yml
ref=v2"
  ["Morrison-Lab/gha/.github/workflows/claude-review.yml@refs/heads/main"]="repo=Morrison-Lab/gha
path=.github/workflows/claude-review.yml
ref=refs/heads/main"
  ["UCD-SERG/serodynamics/.github/workflows/claude-code-review.yml@e088a47d5a510786caf8f5522ac7fd4af9995afd"]="repo=UCD-SERG/serodynamics
path=.github/workflows/claude-code-review.yml
ref=e088a47d5a510786caf8f5522ac7fd4af9995afd"
)

fail=0
for input in "${!cases[@]}"; do
  expected="${cases[$input]}"
  actual="$(bash "$parse_script" "$input")"
  if [[ "$actual" != "$expected" ]]; then
    echo "FAIL: input=$input"
    echo "  expected: $(printf '%s' "$expected" | tr '\n' ' ')"
    echo "  actual:   $(printf '%s' "$actual" | tr '\n' ' ')"
    fail=1
  else
    echo "PASS: $input"
  fi
done

exit "$fail"
