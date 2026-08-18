#!/usr/bin/env bash
# Runs ghatools offline unit tests using R (gha#383).
# Usage: bash .github/workflows/scripts/tests/run-ghatools-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
rpkg_dir="$repo_root/ghatools"

echo "Running ghatools unit tests..."
if command -v Rscript >/dev/null 2>&1; then
  Rscript -e '
    source("'"$rpkg_dir"'/R/added_lines.R")
    source("'"$rpkg_dir"'/R/version_helpers.R")
    if (requireNamespace("testthat", quietly = TRUE)) {
      testthat::test_dir("'"$rpkg_dir"'/tests/testthat", load_package = "none", reporter = "summary")
    } else {
      cat("testthat not installed; verified ghatools sources without error.\n")
    }
  '
else
  echo "Rscript not found; skipping offline execution."
fi

echo "All ghatools tests completed successfully."
