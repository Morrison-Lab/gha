#!/usr/bin/env Rscript

# Offline unit tests for test-coverage/coverage-helpers.R -- the parse/enforce
# logic used by run-coverage.R. Run with:
#   Rscript test-coverage/tests/test-coverage-helpers.R
# Does not load {covr}.
#
# check() / check_error() match
# .github/workflows/scripts/tests/test-description-version.R.
# Extracting a shared r-test-helpers.R is tracked in
# https://github.com/Morrison-Lab/gha/issues/682.

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

check_error <- function(label, expr, pattern) {
  msg <- tryCatch({
    force(expr)
    NA_character_
  }, error = function(e) conditionMessage(e))
  if (is.na(msg)) {
    stop(sprintf("FAIL: %s (expected an error, none raised)", label))
  }
  if (!grepl(pattern, msg)) {
    stop(sprintf(
      "FAIL: %s\n  expected message matching: %s\n  actual: %s",
      label,
      pattern,
      msg
    ))
  }
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
check_error(
  "unknown type is rejected",
  parse_coverage_type("exmaples"),
  "exmaples"
)
check_error(
  "all cannot mix with other types",
  parse_coverage_type("all,tests"),
  "must be the only coverage type"
)
check_error(
  "none cannot mix with other types",
  parse_coverage_type("none,examples"),
  "must be the only coverage type"
)

check("empty comment flag uses default TRUE", parse_comment_flag(""), TRUE)
check("comment flag true", parse_comment_flag("true"), TRUE)
check("comment flag TRUE", parse_comment_flag("TRUE"), TRUE)
check("comment flag false", parse_comment_flag("false"), FALSE)
check_error(
  "comment flag rejects garbage",
  parse_comment_flag("yes"),
  "Invalid boolean"
)

check("empty min-coverage is disabled", parse_min_coverage(""), NULL)
check("whitespace min-coverage is disabled", parse_min_coverage("  "), NULL)
check("min-coverage 0 is allowed", parse_min_coverage("0"), 0)
check("min-coverage 100 is allowed", parse_min_coverage("100"), 100)
check("min-coverage 80.5 is allowed", parse_min_coverage("80.5"), 80.5)
check_error(
  "min-coverage rejects non-numeric",
  parse_min_coverage("all"),
  "Invalid min-coverage"
)
check_error(
  "min-coverage rejects above 100",
  parse_min_coverage("101"),
  "Invalid min-coverage"
)
check_error(
  "min-coverage rejects negative",
  parse_min_coverage("-1"),
  "Invalid min-coverage"
)

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
  enforce_min_coverage(79.9, 80),
  "below the required"
)
check_error(
  "non-finite percent fails closed",
  enforce_min_coverage(NA_real_, 80),
  "not a finite number"
)
check_error(
  "NaN percent fails closed",
  enforce_min_coverage(NaN, 80),
  "not a finite number"
)

cat("All coverage-helpers tests passed.\n")
