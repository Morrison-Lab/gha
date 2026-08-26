#!/usr/bin/env Rscript
# Fail the coverage job when percent coverage is below MIN_COVERAGE.
# Runs as its own composite step so the Cobertura upload can happen first
# (gha#334): a threshold miss should still publish the report this
# capability exists to produce.
#
# Env: COVERAGE_PERCENT, MIN_COVERAGE, RUNNER_TEMP, GITHUB_ACTION_PATH
#
# When the threshold is missed, the error text is also written to
# ${RUNNER_TEMP}/min-coverage-failure.txt. That file is a test hook for
# the selftest coverage job: an outcome=failure alone could be any inner
# crash, so the assertion greps this file for "below the required".

action_path <- Sys.getenv("GITHUB_ACTION_PATH")
if (!nzchar(action_path)) {
  stop(
    "GITHUB_ACTION_PATH is unset; run this script from the composite action.",
    call. = FALSE
  )
}
source(file.path(action_path, "coverage-helpers.R"), local = FALSE)

err_file <- file.path(Sys.getenv("RUNNER_TEMP", tempdir()), "min-coverage-failure.txt")
if (file.exists(err_file)) {
  unlink(err_file)
}

min_pct <- parse_min_coverage(Sys.getenv("MIN_COVERAGE"))
if (is.null(min_pct)) {
  quit(save = "no", status = 0)
}

pct_raw <- Sys.getenv("COVERAGE_PERCENT", "")
pct <- suppressWarnings(as.numeric(pct_raw))
if (!nzchar(pct_raw) || is.na(pct)) {
  stop(
    sprintf(
      "COVERAGE_PERCENT is missing or non-numeric (got %s).",
      pct_raw
    ),
    call. = FALSE
  )
}

tryCatch(
  enforce_min_coverage(pct, min_pct),
  error = function(e) {
    msg <- conditionMessage(e)
    writeLines(msg, err_file)
    stop(msg, call. = FALSE)
  }
)
