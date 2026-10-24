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

# setup-r installs devscripts with ~150 recommended Perl packages, which took
# 18 minutes on a slow mirror (gha#1197). The apt setting must come first.
action="$repo_root/check-ai-tells/action.yml"
no_recommends_line="$(grep -n 'APT::Install-Recommends "false"' "$action" | head -1 | cut -d: -f1)"
setup_r_line="$(grep -n 'r-lib/actions/setup-r@' "$action" | head -1 | cut -d: -f1)"
if [ -z "$no_recommends_line" ] || [ -z "$setup_r_line" ] || [ "$no_recommends_line" -ge "$setup_r_line" ]; then
  echo "::error::check-ai-tells/action.yml must disable apt recommends before setup-r (gha#1197)"
  exit 1
fi

echo "All check-ai-tells test steps completed."
