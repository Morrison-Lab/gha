#!/usr/bin/env bash
# Materialize a tiny R project used to exercise the lint-changed-files
# composite in CI (see the `lint-changed-files` job in _selftest.yml).
#
# Generated at run time rather than committed, so its R sources are not
# swept into the bib or phi jobs' repo-wide scans, per the "generate selftest
# fixtures at runtime" rule in CLAUDE.md.
#
# Two variants, differing in exactly one thing: whether code.R uses `<-` or
# `=`. The fixture's .lintr.R enables only assignment_linter, so a default
# lintr config change on CRAN cannot turn the clean variant red.
set -euo pipefail

usage() {
  echo "usage: make-fixture.sh <dest-dir> [--clean|--dirty]" >&2
  exit 2
}

dest="${1:-}"
[ -n "$dest" ] || usage
variant="${2:-}"
case "$variant" in
  ''|--clean|--dirty) ;;
  *) usage ;;
esac

mkdir -p "$dest"

cat > "$dest/.lintr.R" <<'EOF'
linters <- list(
  assignment_linter = lintr::assignment_linter()
)
EOF

if [ "$variant" = "--dirty" ]; then
  printf '%s\n' "x = 1" > "$dest/code.R"
else
  printf '%s\n' "x <- 1" > "$dest/code.R"
fi
