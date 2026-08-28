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
# (the example-only functions are uncovered by the unit suite), while
# type=examples,vignettes with commentDonttest/commentDontrun=FALSE +
# min-coverage=100 must pass (those flags actually execute the skipped
# blocks). There is no vignettes/ directory: a knitr vignette would pull
# extra Suggested packages into the selftest job, and type=examples,vignettes
# here only proves the comma-split plus the examples comment flags, not
# vignette execution.
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

# Hand-written man/*.Rd files are the source of truth; this fixture never
# runs roxygen, and a regenerate would drop the \donttest{}/\dontrun{}
# examples gha#334's proof rests on.
cat > "$dest/R/add.R" <<'EOF'
add <- function(x, y) {
  x + y
}

from_donttest <- function(x, y) {
  x + y
}

from_dontrun <- function(x, y) {
  x + y
}
EOF

# Unquoted heredoc: $name expands, \name stays literal (backslash is only
# special before $, `, \, and newline).
write_rd() {
  local name="$1"
  local title="$2"
  local description="$3"
  local example="$4"
  cat > "$dest/man/${name}.Rd" <<EOF
\name{${name}}
\alias{${name}}
\title{${title}}
\usage{
${name}(x, y)
}
\arguments{
\item{x}{a number}

\item{y}{a number}
}
\value{
the sum of \code{x} and \code{y}
}
\description{
${description}
}
\examples{
${example}
}
EOF
}

write_rd add "Add two numbers" "Add two numbers." "add(1, 2)"
write_rd from_donttest \
  "Add two numbers (donttest example only)" \
  "Add two numbers. Covered only when donttest examples run." \
  "$(cat <<'EX'
\donttest{
from_donttest(1, 2)
}
EX
)"
write_rd from_dontrun \
  "Add two numbers (dontrun example only)" \
  "Add two numbers. Covered only when dontrun examples run." \
  "$(cat <<'EX'
\dontrun{
from_dontrun(1, 2)
}
EX
)"

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
