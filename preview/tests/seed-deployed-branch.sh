#!/usr/bin/env bash
# Publish a rendered site to a branch on the fixture's bare remote, standing in
# for a previous preview deploy.
#
# Usage: seed-deployed-branch.sh <site-dir> <bare-repo> [branch] [subdir]
set -euo pipefail

site="${1:?usage: seed-deployed-branch.sh <site-dir> <bare-repo> [branch] [subdir]}"
bare="${2:?missing <bare-repo>}"
branch="${3:-gh-pages}"
subdir="${4:-}"

export GIT_AUTHOR_NAME='gha selftest'
export GIT_AUTHOR_EMAIL='selftest@example.invalid'  # phi-allow: synthetic fixture identity, never a real address
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT

target="$staging"
if [ -n "$subdir" ]; then
  target="$staging/$subdir"
  mkdir -p "$target"
fi
cp -r "$site/." "$target/"

git -C "$staging" init --quiet -b "$branch"
git -C "$staging" add -A
git -C "$staging" commit --quiet -m "deployed render"
git -C "$staging" push --quiet --force "$bare" "$branch:$branch"
