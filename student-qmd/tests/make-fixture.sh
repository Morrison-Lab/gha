#!/usr/bin/env bash
# Generate the Quarto projects the `student-qmd` selftest job uses.
#
# Generated rather than committed, for the reason CLAUDE.md gives: a committed
# fixture is swept into OTHER selftest jobs' repo-wide scans (`typos` reads
# its prose, `lint-qmd` its .qmd files).
#
# Layout:
#
#   <root>/good/           a project whose student copy must pass
#     _quarto.yml
#     exercises/t/_exr-a.qmd      a question fragment with its answer
#     hw/hw1.qmd                  includes the fragment by a /-rooted path,
#                                 and hw/parts/_outer.qmd by a relative one
#     hw/parts/_outer.qmd         includes `parts/_inner.qmd`
#     hw/parts/_inner.qmd         where Quarto finds it (relative to hw/)
#     hw/parts/parts/_inner.qmd   where it would be if nested includes
#                                 resolved against the including file
#   <root>/misnamed/       the same project with its answer in a `.solution`
#                          div, which the assign filter does not hide
#
# The two `_inner.qmd` files carry different markers, so the selftest can
# check the generator picks the one Quarto itself picks.
set -euo pipefail

root="${1:?usage: make-fixture.sh <root>}"
rm -rf "$root"
good="$root/good"
mkdir -p "$good/exercises/t" "$good/hw/parts/parts"

printf 'project:\n  type: default\n' > "$good/_quarto.yml"

# The fragment's front matter holds only a comment: a real one names the
# assign filter by path, which this fixture does not install, and Quarto
# merges an included file's front matter into the document it renders.
cat > "$good/exercises/t/_exr-a.qmd" <<'EOF'
---
# a question fragment
---

::: {#exr-a}
State the answer to exercise A.
:::

::: {.sol}
FIXTURE-ANSWER-A
:::
EOF

cat > "$good/hw/hw1.qmd" <<'EOF'
---
title: "Homework 1"
# An instructor note in the front matter.
---

<!-- An instructor note in the body. -->

{{< include /exercises/t/_exr-a.qmd >}}

{{< include parts/_outer.qmd >}}

::: {#exr-b}
What is six times seven?
:::

::: {.sol}
FIXTURE-ANSWER-B
:::
EOF

printf 'Outer part.\n\n{{< include parts/_inner.qmd >}}\n' > "$good/hw/parts/_outer.qmd"
printf 'NESTED-INCLUDE-TOP-DOC-RULE\n' > "$good/hw/parts/_inner.qmd"
printf 'NESTED-INCLUDE-INCLUDING-FILE-RULE\n' > "$good/hw/parts/parts/_inner.qmd"

cp -R "$good" "$root/misnamed"
sed -i.bak 's/^::: {\.sol}$/::: {.solution}/' "$root/misnamed/hw/hw1.qmd"
rm "$root/misnamed/hw/hw1.qmd.bak"
grep -q '^::: {\.solution}$' "$root/misnamed/hw/hw1.qmd"
