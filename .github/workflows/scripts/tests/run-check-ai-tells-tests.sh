#!/usr/bin/env bash
# Runs check-ai-tells offline unit tests and fixture validations (gha#382).
# Usage: bash .github/workflows/scripts/tests/run-check-ai-tells-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
test_file="$repo_root/check-ai-tells/tests/test-check-ai-tells.R"

echo "Running check-ai-tells tests..."
if command -v Rscript >/dev/null 2>&1; then
  Rscript "$test_file"
else
  echo "Rscript not found; skipping offline execution."
fi

echo "All check-ai-tells test steps completed."
