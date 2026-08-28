# Shared check()/check_error() harness for this repo's offline R test suites.
# Source it from a candidates list so a suite runs from the repo root, from
# its component's own directory, and from its tests/ directory, e.g.:
#   for (p in c(".github/workflows/scripts/tests/r-test-helpers.R",
#               "../.github/workflows/scripts/tests/r-test-helpers.R",
#               "../../.github/workflows/scripts/tests/r-test-helpers.R")) { ... }
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
  # Capture the condition object rather than its message: a condition object
  # is never NULL, so this stays correct for an error whose message is NA,
  # where a message-sentinel test would misreport "none raised".
  err <- tryCatch({
    force(expr)
    NULL
  }, error = function(e) e)
  if (is.null(err)) {
    stop(sprintf("FAIL: %s (expected an error, none raised)", label))
  }
  # conditionMessage() can be a length > 1 vector for a custom condition,
  # which would make the if () below a fatal length > 1 error; collapse it.
  msg <- paste(conditionMessage(err), collapse = "\n")
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
