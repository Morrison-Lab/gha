#!/usr/bin/env Rscript
# Measure package coverage with covr and write cobertura.xml.
# Threshold enforcement is a later composite step (enforce-min-coverage.R)
# so the Cobertura upload still runs when coverage is below the bar (gha#334).
#
# Env (set by test-coverage/action.yml):
#   COVERAGE_PATH, COVERAGE_TYPE, COVERAGE_COMMENT_DONTTEST,
#   COVERAGE_COMMENT_DONTRUN, RUNNER_TEMP, GITHUB_OUTPUT

args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
if (length(file_arg) != 1L) {
  stop("Unable to locate run-coverage.R via --file=", call. = FALSE)
}
script_dir <- dirname(normalizePath(sub("^--file=", "", file_arg)))
source(file.path(script_dir, "coverage-helpers.R"), local = FALSE)

suppressPackageStartupMessages({
  if (!requireNamespace("covr", quietly = TRUE)) {
    stop("Package 'covr' is not installed.")
  }
})

path <- Sys.getenv("COVERAGE_PATH", ".")
type <- parse_coverage_type(Sys.getenv("COVERAGE_TYPE", "tests"))
comment_donttest <- parse_comment_flag(
  Sys.getenv("COVERAGE_COMMENT_DONTTEST", "true"),
  default = TRUE
)
comment_dontrun <- parse_comment_flag(
  Sys.getenv("COVERAGE_COMMENT_DONTRUN", "true"),
  default = TRUE
)
runner_temp <- Sys.getenv("RUNNER_TEMP", tempdir())

options(crayon.enabled = TRUE)
coverage <- covr::package_coverage(
  path = path,
  type = type,
  quiet = FALSE,
  clean = FALSE,
  commentDonttest = comment_donttest,
  commentDontrun = comment_dontrun,
  install_path = file.path(
    normalizePath(runner_temp, winslash = "/"),
    "package"
  )
)
pct <- covr::percent_coverage(coverage)
cat(sprintf("\nCode coverage: %.2f%%\n", pct))
# Written to the working directory as cobertura.xml regardless of `path`.
covr::to_cobertura(coverage)
github_output <- Sys.getenv("GITHUB_OUTPUT", "")
if (nzchar(github_output)) {
  cat(sprintf("percent=%.10g\n", pct), file = github_output, append = TRUE)
}
