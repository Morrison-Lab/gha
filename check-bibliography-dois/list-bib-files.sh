#!/usr/bin/env bash
# Print the .bib files `check-bibliography-dois` should check, NUL-delimited.
#
# A file inside a git submodule is skipped by default: it belongs to another
# repository, which checks it under its own exclusion list.
# A submodule's files are present in the workspace only when something put them
# there (a `submodules:` checkout, or a leftover from an earlier job on a
# self-hosted runner that reuses its work directory), so scanning them made the
# verdict depend on the runner's history rather than on the repository.
#
# Submodules are read from the index as gitlinks (mode 160000), not from
# .gitmodules, so a stale or missing .gitmodules cannot hide one.
#
# Environment:
#   INCLUDE_SUBMODULES  "true" to include files under submodules (default: false)
#
# Usage: list-bib-files.sh [directory]   (default: current directory)
set -euo pipefail

root="${1:-.}"
cd "$root"

prune=()
if [ "${INCLUDE_SUBMODULES:-false}" != "true" ] \
  && git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    prune+=(-path "./$path" -prune -o)
  done < <(git ls-files --stage | awk -F'\t' '/^160000 /{print $2}')
fi

find . "${prune[@]}" -name "*.bib" -not -path "./.git/*" -print0
