#!/usr/bin/env bash
# Build a throwaway Quarto website fixture for the changed-chapters selftest.
#
# Generated at run time rather than committed: a committed HTML or .qmd fixture
# gets swept into the `phi`, `bib`, `typos` and `lint-qmd` jobs' own repo-wide
# scans (see CLAUDE.md, "Generate selftest fixtures at runtime").
#
# Usage: make-fixture.sh <dir>
#
# Creates <dir>/origin.git   -- a bare repo standing in for the caller's remote
#         <dir>/work         -- a Quarto website whose `origin` is that bare repo
set -euo pipefail

root="${1:?usage: make-fixture.sh <dir>}"
rm -rf "$root"
mkdir -p "$root"
root=$(cd "$root" && pwd)

export GIT_AUTHOR_NAME='gha selftest'
export GIT_AUTHOR_EMAIL='selftest@example.invalid'  # phi-allow: synthetic fixture identity, never a real address
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

git init --quiet --bare -b main "$root/origin.git"

work="$root/work"
mkdir -p "$work/chapters"

cat > "$work/_quarto.yml" <<'YAML'
project:
  type: website
  output-dir: _site
website:
  title: "changed-chapters fixture"
format:
  html:
    theme: default
YAML

cat > "$work/index.qmd" <<'QMD'
---
title: "Home"
---

The preview home page.
QMD

cat > "$work/chapters/01.qmd" <<'QMD'
---
title: "Chapter one"
---

The first chapter, which this fixture never edits.
QMD

cat > "$work/chapters/02.qmd" <<'QMD'
---
title: "Chapter two"
---

The second chapter, which the selftest edits to prove a real edit is reported.
QMD

git -C "$work" init --quiet -b main
# file:// rather than a plain path: git ignores --depth over the local
# transport, and the detector's fetch is deliberately shallow.
git -C "$work" remote add origin "file://$root/origin.git"
git -C "$work" add -A
git -C "$work" commit --quiet -m 'fixture site'

echo "$root"
