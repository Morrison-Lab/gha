#!/usr/bin/env bash
# Materialize a tiny git repo used to exercise the check-typos composite in
# CI (see the `typos` job in .github/workflows/_selftest.yml).
#
# Generated at run time rather than committed, per the "generate selftest
# fixtures at runtime" rule in CLAUDE.md. The known misspelling is written
# only into the throwaway checkout; this script splits the token so a later
# whole-tree scan of gha does not flag the generator itself.
#
# Layout (two commits):
#   1. CONTRIBUTING.md with a known misspelling -- pre-existing drift.
#   2. notes.md with clean prose -- an unrelated addition.
# So a diff against HEAD~1 must NOT flag the CONTRIBUTING.md typo, while
# `base-ref: all` must. A third commit (optional `--new-typo`) adds
# `page.qmd` with the same misspelling, which the diff-scoped path must flag --
# that is the gap spellcheck.yml cannot see.
set -euo pipefail

usage() {
  echo "usage: make-fixture.sh <dest-dir> [--new-typo]" >&2
  exit 2
}

[ "${1:-}" ] || usage
dest=$1
shift
new_typo=false
while [ "${1:-}" ]; do
  case "$1" in
    --new-typo) new_typo=true ;;
    *) usage ;;
  esac
  shift
done

rm -rf "$dest"
mkdir -p "$dest"
git -C "$dest" init -q
git -C "$dest" config user.email t@example.invalid
git -C "$dest" config user.name t
git -C "$dest" config commit.gpgsign false

# Split so this generator is not itself a typos hit.
typo="$(printf '%s%s' reci eve)"
printf 'Please %s this contribution.\n' "$typo" > "$dest/CONTRIBUTING.md"
git -C "$dest" add CONTRIBUTING.md
git -C "$dest" commit -qm 'pre-existing typo'

printf 'A short note with no misspelling.\n' > "$dest/notes.md"
git -C "$dest" add notes.md
git -C "$dest" commit -qm 'unrelated addition'

if [ "$new_typo" = true ]; then
  printf '# Page\n\nThis will %s a heading.\n' "$typo" > "$dest/page.qmd"
  git -C "$dest" add page.qmd
  git -C "$dest" commit -qm 'new quarto typo'
fi
