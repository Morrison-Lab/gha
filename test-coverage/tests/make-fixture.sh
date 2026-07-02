#!/usr/bin/env bash
# Materialize a minimal R package used to exercise the test-coverage composite
# in CI (see the `coverage` job in .github/workflows/_selftest.yml).
#
# The package is generated at run time rather than committed so its R sources
# and DESCRIPTION are not discovered by the repo-wide R dependency scanning that
# other selftest jobs run (e.g. the bib job's `deps::.` resolution), which would
# otherwise fail trying to install the fixture's own `covfixture` package.
set -euo pipefail

dest="${1:?usage: make-fixture.sh <dest-dir>}"
mkdir -p "$dest/R" "$dest/tests/testthat"

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
