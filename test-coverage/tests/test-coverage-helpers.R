#!/usr/bin/env Rscript

# Offline unit tests for test-coverage/coverage-helpers.R -- the parse/enforce
# logic used by run-coverage.R. Run with:
#   Rscript test-coverage/tests/test-coverage-helpers.R
# Does not load {covr}; a missing R is a skip for local runs, not a green pass.

sourced <- FALSE
candidates <- c(
  "test-coverage/coverage-helpers.R",
  "../coverage-helpers.R",
  "coverage-helpers.R"
)
for (p in candidates) {
  if (file.exists(p)) {
    source(p)
    sourced <- TRUE
    break
  }
}
if (!sourced) stop("could not locate coverage-helpers.R")

check <- function(label, actual, expected) {
  if (!identical(actual, expected)) {
    stop(sprintf(
      "FAIL: %s\n  expected: %s\n  actual:   %s",
      label,
      paste(deparse(expected), collapse = " "),
      paste(deparse(actual), collapse = " ")
    ))
  }
  cat(sprintf("ok - %s\n", label))
}

check_error <- function(label, expr) {
  ok <- tryCatch({
    force(expr)
    FALSE
  }, error = function(e) TRUE)
  if (!ok) stop(sprintf("FAIL: %s (expected an error, none raised)", label))
  cat(sprintf("ok - %s\n", label))
}

check("empty type defaults to tests", parse_coverage_type(""), "tests")
check(
  "whitespace-only type defaults to tests",
  parse_coverage_type("   "),
  "tests"
)
check("single type", parse_coverage_type("tests"), "tests")
check(
  "comma-separated types are split and trimmed",
  parse_coverage_type("examples, vignettes"),
  c("examples", "vignettes")
)
check(
  "trailing comma does not add an empty type",
  parse_coverage_type("examples,"),
  "examples"
)

check("empty comment flag uses default TRUE", parse_comment_flag(""), TRUE)
check(
  "empty comment flag can default FALSE",
  parse_comment_flag("", default = FALSE),
  FALSE
)
check("comment flag true", parse_comment_flag("true"), TRUE)
check("comment flag TRUE", parse_comment_flag("TRUE"), TRUE)
check("comment flag false", parse_comment_flag("false"), FALSE)
check_error("comment flag rejects garbage", parse_comment_flag("yes"))

check("empty min-coverage is disabled", parse_min_coverage(""), NULL)
check("whitespace min-coverage is disabled", parse_min_coverage("  "), NULL)
check("min-coverage 0 is allowed", parse_min_coverage("0"), 0)
check("min-coverage 100 is allowed", parse_min_coverage("100"), 100)
check("min-coverage 80.5 is allowed", parse_min_coverage("80.5"), 80.5)
check_error("min-coverage rejects non-numeric", parse_min_coverage("all"))
check_error("min-coverage rejects above 100", parse_min_coverage("101"))
check_error("min-coverage rejects negative", parse_min_coverage("-1"))

check(
  "disabled threshold never fails",
  enforce_min_coverage(0, NULL),
  0
)
check(
  "coverage equal to the bar passes",
  enforce_min_coverage(80, 80),
  80
)
check(
  "coverage above the bar passes",
  enforce_min_coverage(90, 80),
  90
)
check_error(
  "coverage below the bar fails",
  enforce_min_coverage(79.9, 80)
)

cat("All coverage-helpers tests passed.\n")
