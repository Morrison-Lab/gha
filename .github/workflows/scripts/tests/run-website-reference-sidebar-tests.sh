#!/usr/bin/env bash
# run-website-reference-sidebar-tests.sh
# Asserts that every website/reference/*.qmd reference page has a corresponding
# sidebar entry in website/_quarto.yml (gha#430).

set -euo pipefail

missing=0
count=0

for f in website/reference/*.qmd; do
  [[ -e "$f" ]] || continue
  b=$(basename "$f")
  count=$((count + 1))
  if ! grep -q "reference/$b" website/_quarto.yml; then
    echo "::error::$b missing from website/_quarto.yml sidebar" >&2
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo "::error::One or more website reference pages are missing from website/_quarto.yml sidebar." >&2
  exit 1
fi

echo "OK   All $count reference pages present in website/_quarto.yml sidebar"
