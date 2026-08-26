#!/usr/bin/env Rscript
# Fail the coverage job when percent coverage is below MIN_COVERAGE.
# Runs as its own composite step so the Cobertura upload can happen first
# (gha#334): a threshold miss should still publish the report this
# capability exists to produce.
#
# Env: COVERAGE_PERCENT, MIN_COVERAGE, RUNNER_TEMP (optional failure file)

args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
if (length(file_arg) != 1L) {
  stop("Unable to locate enforce-min-coverage.R via --file=", call. = FALSE)
}
script_dir <- dirname(normalizePath(sub("^--file=", "", file_arg)))
source(file.path(script_dir, "coverage-helpers.R"), local = FALSE)

err_file <- file.path(Sys.getenv("RUNNER_TEMP", tempdir()), "min-coverage-failure.txt")
if (file.exists(err_file)) {
  unlink(err_file)
}

min_pct <- parse_min_coverage(Sys.getenv("MIN_COVERAGE", ""))
if (is.null(min_pct)) {
  quit(save = "no", status = 0)
}

pct_raw <- Sys.getenv("COVERAGE_PERCENT", "")
pct <- suppressWarnings(as.numeric(pct_raw))
if (!nzchar(pct_raw) || length(pct) != 1L || is.na(pct)) {
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
