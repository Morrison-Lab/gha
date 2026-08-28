# Shared check()/check_error() harness for this repo's offline R test suites.
# Source it from a candidates list so a suite runs both from the repo root
# and from its own directory, e.g.:
#   for (p in c(".github/workflows/scripts/tests/r-test-helpers.R",
#               "../../.github/workflows/scripts/tests/r-test-helpers.R",
#               "r-test-helpers.R")) { ... }
# Extracted from test-coverage/tests/test-coverage-helpers.R and
# .github/workflows/scripts/tests/test-description-version.R, whose local
# copies had drifted (https://github.com/Morrison-Lab/gha/issues/682).

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

check_error <- function(label, expr, pattern = NULL, fixed = FALSE) {
  msg <- tryCatch({
    force(expr)
    NA_character_
  }, error = function(e) conditionMessage(e))
  if (is.na(msg)) {
    stop(sprintf("FAIL: %s (expected an error, none raised)", label))
  }
  if (!is.null(pattern) && !grepl(pattern, msg, fixed = fixed)) {
    stop(sprintf(
      "FAIL: %s\n  expected message matching: %s\n  actual: %s",
      label,
      pattern,
      msg
    ))
  }
  cat(sprintf("ok - %s\n", label))
}