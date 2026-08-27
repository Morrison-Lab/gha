#!/usr/bin/env bash
# Materialize a minimal R package used to exercise the check-extra composite
# in CI (see the `check-extra` job in .github/workflows/_selftest.yml).
#
# Generated at run time rather than committed so its DESCRIPTION/R sources
# are not discovered by the repo-wide R dependency scanning that other
# selftest jobs run (the same reason test-coverage/tests/make-fixture.sh
# exists).
set -euo pipefail

dest="${1:?usage: make-fixture.sh <dest-dir> [--warn-example|--stale-readme|--no-readme]}"
shift || true

warn_example=false
stale_readme=false
no_readme=false
for arg in "$@"; do
  case "$arg" in
    --warn-example) warn_example=true ;;
    --stale-readme) stale_readme=true ;;
    --no-readme) no_readme=true ;;
    *)
      echo "unknown flag: $arg" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$dest/R" "$dest/man" "$dest/tests/testthat" "$dest/vignettes"

cat > "$dest/DESCRIPTION" <<'EOF'
Package: extrafixture
Title: Extra-Check Selftest Fixture
Version: 0.0.1
Authors@R:
    person("Selftest", "Fixture", , "fixture@example.com", role = c("aut", "cre"))
Description: A minimal package that exercises the check-extra composite in CI.
License: MIT
Encoding: UTF-8
Suggests:
    knitr,
    rmarkdown,
    testthat (>= 3.0.0)
VignetteBuilder: knitr
Config/testthat/edition: 3
EOF

cat > "$dest/NAMESPACE" <<'EOF'
export(add)
EOF

cat > "$dest/R/add.R" <<'EOF'
add <- function(x, y) {
  x + y
}
EOF

if [ "$warn_example" = true ]; then
  cat > "$dest/man/add.Rd" <<'EOF'
\name{add}
\alias{add}
\title{Add two numbers}
\usage{add(x, y)}
\arguments{
\item{x}{a number}
\item{y}{a number}
}
\description{Add two numbers.}
\examples{
warning("boom from extrafixture example")
add(1, 2)
}
EOF
else
  cat > "$dest/man/add.Rd" <<'EOF'
\name{add}
\alias{add}
\title{Add two numbers}
\usage{add(x, y)}
\arguments{
\item{x}{a number}
\item{y}{a number}
}
\description{Add two numbers.}
\examples{
add(1, 2)
}
EOF
fi

cat > "$dest/tests/testthat.R" <<'EOF'
library(testthat)
library(extrafixture)

test_check("extrafixture")
EOF

cat > "$dest/tests/testthat/test-add.R" <<'EOF'
test_that("add sums its arguments", {
  expect_equal(add(2, 3), 5)
})
EOF

cat > "$dest/vignettes/extrafixture.Rmd" <<'EOF'
---
title: "extrafixture"
output: rmarkdown::html_vignette
vignette: >
  %\VignetteIndexEntry{extrafixture}
  %\VignetteEngine{knitr::rmarkdown}
  %\VignetteEncoding{UTF-8}
---

```{r, include = FALSE}
knitr::opts_chunk$set(collapse = TRUE, comment = "#>")
```

```{r}
extrafixture::add(1, 2)
```
EOF

if [ "$no_readme" != true ]; then
  cat > "$dest/README.Rmd" <<'EOF'
---
output: github_document
---

# extrafixture

```{r}
extrafixture::add(1, 2)
```
EOF

  if [ "$stale_readme" = true ]; then
    cat > "$dest/README.md" <<'EOF'
# extrafixture

This knitted README.md does not match README.Rmd.
EOF
  else
    # A committed README.md is not required for the warnings / random-order
    # checks. The readme check's freshness half is unit-tested separately;
    # the selftest composite call for `readme` opts out of freshness because
    # github_document's exact output is not something this generator can
    # pin without running pandoc here.
    cat > "$dest/README.md" <<'EOF'
# extrafixture

Placeholder knitted README. The readme selftest call sets
check-readme-freshness: false so this file is not compared.
EOF
  fi
fi

echo "Created R package fixture at: $dest"
