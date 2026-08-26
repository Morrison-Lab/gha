#!/usr/bin/env bash
# Materialize a minimal R package used to exercise the test-coverage composite
# in CI (see the `coverage` job in .github/workflows/_selftest.yml).
#
# The package is generated at run time rather than committed so its R sources
# and DESCRIPTION are not discovered by the repo-wide R dependency scanning that
# other selftest jobs run (e.g. the bib job's `deps::.` resolution), which would
# otherwise fail trying to install the fixture's own `covfixture` package.
#
# The fixture has three exported functions:
#   add()            -- covered by the unit test
#   from_donttest()  -- covered only by a \donttest{} Rd example
#   from_dontrun()   -- covered only by a \dontrun{} Rd example
# That split is load-bearing for gha#334: tests + min-coverage=100 must fail
# (the example-only functions are uncovered), while type=examples,vignettes
# with commentDonttest/commentDontrun=FALSE + min-coverage=100 must pass
# (those flags actually execute the skipped blocks).
set -euo pipefail

dest="${1:?usage: make-fixture.sh <dest-dir>}"
mkdir -p "$dest/R" "$dest/man" "$dest/tests/testthat"

cat > "$dest/DESCRIPTION" <<'EOF'
Package: covfixture
Title: Coverage Selftest Fixture
Version: 0.0.1
Authors@R:
    person("Selftest", "Fixture", , "selftest@example.com", role = c("aut", "cre"))
Description: A minimal package that exercises the test-coverage composite in CI.
License: GPL-3
Encoding: UTF-8
Suggests:
    testthat (>= 3.0.0)
Config/testthat/edition: 3
EOF

cat > "$dest/NAMESPACE" <<'EOF'
export(add)
export(from_donttest)
export(from_dontrun)
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

#' Add two numbers (donttest example only)
#'
#' @param x a number
#' @param y a number
#' @return the sum of `x` and `y`
#' @export
from_donttest <- function(x, y) {
  x + y
}

#' Add two numbers (dontrun example only)
#'
#' @param x a number
#' @param y a number
#' @return the sum of `x` and `y`
#' @export
from_dontrun <- function(x, y) {
  x + y
}
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
Add two numbers.
}
\examples{
add(1, 2)
}
EOF

cat > "$dest/man/from_donttest.Rd" <<'EOF'
\name{from_donttest}
\alias{from_donttest}
\title{Add two numbers (donttest example only)}
\usage{
from_donttest(x, y)
}
\arguments{
\item{x}{a number}

\item{y}{a number}
}
\value{
the sum of \code{x} and \code{y}
}
\description{
Add two numbers. Covered only when donttest examples run.
}
\examples{
\donttest{
from_donttest(1, 2)
}
}
EOF

cat > "$dest/man/from_dontrun.Rd" <<'EOF'
\name{from_dontrun}
\alias{from_dontrun}
\title{Add two numbers (dontrun example only)}
\usage{
from_dontrun(x, y)
}
\arguments{
\item{x}{a number}

\item{y}{a number}
}
\value{
the sum of \code{x} and \code{y}
}
\description{
Add two numbers. Covered only when dontrun examples run.
}
\examples{
\dontrun{
from_dontrun(1, 2)
}
}
EOF

cat > "$dest/tests/testthat.R" <<'EOF'
library(testthat)
library(covfixture)

test_check("covfixture")
EOF

cat > "$dest/tests/testthat/test-add.R" <<'EOF'
test_that("add sums its arguments", {
  expect_equal(add(2, 3), 5)
})
EOF

echo "Created R package fixture at: $dest"
