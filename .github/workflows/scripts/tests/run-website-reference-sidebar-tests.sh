#!/usr/bin/env bash
# run-website-reference-sidebar-tests.sh
# Asserts that every website/reference/*.qmd reference page has a corresponding
# sidebar entry in website/_quarto.yml (gha#430).
#
# Usage:
#   bash run-website-reference-sidebar-tests.sh [--dir <ref_dir>] [--config <quarto_yml>] [--self-test]

set -euo pipefail

dir="website/reference"
config="website/_quarto.yml"
self_test=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      dir="$2"
      shift 2
      ;;
    --config)
      config="$2"
      shift 2
      ;;
    --self-test)
      self_test=true
      shift 1
      ;;
    *)
      echo "::error::Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$self_test" == "true" ]]; then
  echo "Running run-website-reference-sidebar-tests offline unit tests..."
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT

  mkdir -p "$tmpdir/ref"
  touch "$tmpdir/ref/a.qmd"
  touch "$tmpdir/ref/b.qmd"
  cat <<'EOF' > "$tmpdir/_quarto.yml"
sidebar:
  contents:
    - section: "Reference"
      contents:
        - reference/a.qmd
EOF

  if bash "$0" --dir "$tmpdir/ref" --config "$tmpdir/_quarto.yml" >/dev/null 2>&1; then
    echo "::error::Expected run-website-reference-sidebar-tests to fail on missing b.qmd" >&2
    exit 1
  fi
  echo "OK   run-website-reference-sidebar-tests failed as expected when b.qmd is missing"

  cat <<'EOF' > "$tmpdir/_quarto.yml"
sidebar:
  contents:
    - section: "Reference"
      contents:
        - reference/a.qmd
        - reference/b.qmd
EOF

  if ! bash "$0" --dir "$tmpdir/ref" --config "$tmpdir/_quarto.yml" >/dev/null 2>&1; then
    echo "::error::Expected run-website-reference-sidebar-tests to pass when all pages present" >&2
    exit 1
  fi
  echo "OK   run-website-reference-sidebar-tests passed as expected when all pages present"

  echo "All run-website-reference-sidebar-tests offline unit tests passed."
  exit 0
fi

if [[ ! -d "$dir" ]]; then
  echo "::error::Reference directory '$dir' does not exist" >&2
  exit 1
fi

if [[ ! -f "$config" ]]; then
  echo "::error::Quarto config file '$config' does not exist" >&2
  exit 1
fi

missing=0
count=0

for f in "$dir"/*.qmd; do
  [[ -e "$f" ]] || continue
  b=$(basename "$f")
  count=$((count + 1))
  if ! grep -q "reference/$b" "$config"; then
    echo "::error::$b missing from $config sidebar" >&2
    missing=1
  fi
done

if [[ "$count" -eq 0 ]]; then
  echo "::error::No reference pages found in $dir" >&2
  exit 1
fi

if [[ "$missing" -ne 0 ]]; then
  echo "::error::One or more reference pages are missing from $config sidebar." >&2
  exit 1
fi

echo "OK   All $count reference pages present in $config sidebar"
