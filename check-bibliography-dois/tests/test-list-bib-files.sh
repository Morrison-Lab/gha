#!/usr/bin/env bash
# Offline tests for list-bib-files.sh: a .bib file under a git submodule is
# skipped unless INCLUDE_SUBMODULES=true, whether or not .gitmodules exists
# and whatever the submodule's files look like in the workspace.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/../list-bib-files.sh"
fail=0

check() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "ok   - $name"
  else
    echo "FAIL - $name"
    echo "  expected: $expected"
    echo "  actual:   $actual"
    fail=1
  fi
}

# One sorted, newline-separated list from the NUL-delimited output.
listing() {
  "$script" "$1" | tr '\0' '\n' | sort | paste -sd, -
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

repo="$work/repo"
mkdir -p "$repo/chapters" "$repo/macros/nested" "$repo/plain dir"
git -C "$repo" init -q
git -C "$repo" config user.email test@example.invalid # phi-allow
git -C "$repo" config user.name test
echo '@book{a, title={A}}' > "$repo/references.bib"
echo '@book{b, title={B}}' > "$repo/chapters/more.bib"
echo '@book{c, title={C}}' > "$repo/plain dir/spaced.bib"
echo '@book{d, title={D}}' > "$repo/macros/references.bib"
echo '@book{e, title={E}}' > "$repo/macros/nested/deep.bib"
git -C "$repo" add references.bib chapters "plain dir"
git -C "$repo" commit -q -m files
# Register ./macros as a submodule (a gitlink), the way `git submodule add`
# does, without needing a second repository.
sha="$(git -C "$repo" rev-parse HEAD)"
git -C "$repo" update-index --add --cacheinfo "160000,$sha,macros"

base="./chapters/more.bib,./plain dir/spaced.bib,./references.bib"
all="$base,./macros/nested/deep.bib,./macros/references.bib"
all="$(printf '%s' "$all" | tr ',' '\n' | sort | paste -sd, -)"

check "submodule files skipped by default" "$base" "$(listing "$repo")"
check "INCLUDE_SUBMODULES=false skips them" "$base" \
  "$(INCLUDE_SUBMODULES=false listing "$repo")"
check "INCLUDE_SUBMODULES=true includes them" "$all" \
  "$(INCLUDE_SUBMODULES=true listing "$repo")"

# No .gitmodules is needed: the index alone names the submodule.
test ! -e "$repo/.gitmodules"
check "no .gitmodules file is required" "$base" "$(listing "$repo")"

# The submodule's files absent from the workspace changes nothing.
rm -rf "$repo/macros"
check "absent submodule files give the same list" "$base" "$(listing "$repo")"

# A directory that is not a git work tree is scanned whole.
plain="$work/plain"
mkdir -p "$plain/sub"
echo '@book{f, title={F}}' > "$plain/sub/x.bib"
check "outside a git work tree everything is scanned" "./sub/x.bib" \
  "$(listing "$plain")"

# Only the submodule path is pruned, not a sibling that shares its prefix.
repo2="$work/repo2"
mkdir -p "$repo2/macros-extra"
git -C "$repo2" init -q
echo '@book{g, title={G}}' > "$repo2/macros-extra/keep.bib"
git -C "$repo2" add macros-extra
git -C "$repo2" -c user.email=t@example.invalid -c user.name=t commit -q -m x # phi-allow
sha2="$(git -C "$repo2" rev-parse HEAD)"
git -C "$repo2" update-index --add --cacheinfo "160000,$sha2,macros"
check "a sibling sharing the submodule's prefix is kept" \
  "./macros-extra/keep.bib" "$(listing "$repo2")"

exit "$fail"
