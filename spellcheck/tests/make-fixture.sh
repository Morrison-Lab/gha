#!/usr/bin/env bash
# Materialize a minimal R package used to exercise the spellcheck composite in
# CI (see the `spellcheck` job in .github/workflows/_selftest.yml).
#
# The package is generated at run time rather than committed, so its DESCRIPTION
# and R sources are not discovered by the repo-wide R dependency scanning other
# selftest jobs run (the bib job's `deps::.` resolution would try to install the
# fixture's own package), per the "generate selftest fixtures at runtime" rule
# in CLAUDE.md.
#
# Two variants, differing in EXACTLY ONE thing: whether inst/WORDLIST exists.
# Both carry the same domain term, `seroincidence`, which hunspell's en_US
# dictionary does not know (measured 2026-08-21: hunspell_check() returns FALSE
# for it, and TRUE for "spellcheck", which is why that more obvious candidate
# was not used). So the clean variant passing and the dirty variant failing
# together pin two things at once -- that unknown words are detected at all, and
# that inst/WORDLIST is what suppresses them -- rather than only the first,
# which a fixture carrying a plain misspelling would leave untested.
#
# The term appears in the DESCRIPTION's Description field AND in a root
# README.md, because spell_check_package() reads root readme/news/changes/index
# Markdown as well as DESCRIPTION, man/*.Rd, and vignettes. That surface is easy
# to document wrong -- this capability's own docs did, until a fixture showed
# otherwise -- so the fixture pins it rather than leaving it to prose.
set -euo pipefail

usage() {
  echo "usage: make-fixture.sh <dest-dir> [--no-wordlist]" >&2
  exit 2
}

dest="${1:-}"
[ -n "$dest" ] || usage
variant="${2:-}"
case "$variant" in
  ''|--no-wordlist) ;;
  *) usage ;;
esac

mkdir -p "$dest/R" "$dest/man" "$dest/inst"

cat > "$dest/DESCRIPTION" <<'EOF'
Package: spellfixture
Title: Spellcheck Selftest Fixture
Version: 0.0.1
Authors@R:
    person("Selftest", "Fixture", , "selftest@example.com", role = c("aut", "cre"))
Description: A minimal package that exercises the spellcheck composite in CI.
    It mentions seroincidence so the check has a term to decide about.
License: GPL-3
Encoding: UTF-8
Language: en-US
EOF

cat > "$dest/NAMESPACE" <<'EOF'
export(add)
EOF

cat > "$dest/R/add.R" <<'EOF'
#' Add two numbers
#'
#' @param x a number
#' @param y a number
#' @return the sum of `x` and `y`
#' @export
add <- function(x, y) {
  x + y
}
EOF

cat > "$dest/README.md" <<'EOF'
# spellfixture

A minimal package used to exercise the spellcheck composite.
It reports seroincidence, so this file is a second surface the check must read.
EOF

cat > "$dest/man/add.Rd" <<'EOF'
\name{add}
\alias{add}
\title{Add two numbers}
\usage{
add(x, y)
}
\arguments{
  \item{x}{a number}
  \item{y}{a number}
}
\value{
the sum of \code{x} and \code{y}
}
\description{
Add two numbers together.
}
EOF

if [ "$variant" = "--no-wordlist" ]; then
  echo "Created R package fixture WITHOUT inst/WORDLIST at: $dest"
else
  cat > "$dest/inst/WORDLIST" <<'EOF'
seroincidence
EOF
  echo "Created R package fixture with inst/WORDLIST at: $dest"
fi
