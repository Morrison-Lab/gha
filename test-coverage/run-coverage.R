#!/usr/bin/env Rscript
# Measure package coverage with covr and write cobertura.xml.
# Threshold enforcement is a later composite step (enforce-min-coverage.R)
# so the Cobertura upload still runs when coverage is below the bar (gha#334).
#
# Adapted from r-lib/actions test-coverage.yaml and
# IndrajeetPatil/workflows test-coverage.yaml (MIT).
#
# Env (set by test-coverage/action.yml):
#   COVERAGE_PATH, COVERAGE_TYPE, COVERAGE_COMMENT_DONTTEST,
#   COVERAGE_COMMENT_DONTRUN, RUNNER_TEMP, GITHUB_OUTPUT,
#   GITHUB_ACTION_PATH, GITHUB_STEP_SUMMARY

action_path <- Sys.getenv("GITHUB_ACTION_PATH")
if (!nzchar(action_path)) {
  stop(
    "GITHUB_ACTION_PATH is unset; run this script from the composite action.",
    call. = FALSE
  )
}
source(file.path(action_path, "coverage-helpers.R"), local = FALSE)

# Fail fast on a bad min-coverage value before covr installs the package.
# Enforcement still happens after the Codecov upload.
invisible(parse_min_coverage(Sys.getenv("MIN_COVERAGE")))

if (!requireNamespace("covr", quietly = TRUE)) {
  stop("Package 'covr' is not installed.", call. = FALSE)
}

path <- Sys.getenv("COVERAGE_PATH")
type <- parse_coverage_type(Sys.getenv("COVERAGE_TYPE"))
comment_donttest <- parse_comment_flag(
  Sys.getenv("COVERAGE_COMMENT_DONTTEST")
)
comment_dontrun <- parse_comment_flag(
  Sys.getenv("COVERAGE_COMMENT_DONTRUN")
)
runner_temp <- Sys.getenv("RUNNER_TEMP")
if (!nzchar(runner_temp)) {
  runner_temp <- tempdir()
}

install_path <- file.path(
  normalizePath(runner_temp, winslash = "/"),
  "package"
)
# covr with clean=FALSE reuses this directory across composite calls in the
# same job (the selftest coverage job runs three). A leftover rdb from a
# previous install is corrupt on the next load.
if (unlink(install_path, recursive = TRUE, force = TRUE) != 0L) {
  stop(
    sprintf("could not remove stale covr install tree at %s.", install_path),
    call. = FALSE
  )
}

github_output <- Sys.getenv("GITHUB_OUTPUT", "")
if (nzchar(github_output)) {
  cat(
    sprintf("install_path=%s\n", install_path),
    file = github_output,
    append = TRUE
  )
}

# Copied from r-lib/actions test-coverage.yaml so covr's progress output is
# colored on the runner.
options(crayon.enabled = TRUE)

covr_args <- list(
  path = path,
  type = type,
  quiet = FALSE,
  clean = FALSE,
  install_path = install_path
)
# commentDonttest/commentDontrun are not named arguments of
# covr::package_coverage(); they travel through `...` to
# tools::testInstalledPackage() and then to the unexported
# tools:::.createExdotR() / tools::Rd2ex() helpers. The selftest's
# type=examples,vignettes call with both flags false is what pins that
# pass-through: if it broke, from_donttest/from_dontrun would stay
# uncovered and min-coverage=100 would fail that step.
if (any(type %in% c("examples", "all"))) {
  covr_args$commentDonttest <- comment_donttest
  covr_args$commentDontrun <- comment_dontrun
}

coverage <- do.call(covr::package_coverage, covr_args)
pct <- covr::percent_coverage(coverage)
cat(sprintf("\nCode coverage: %.2f%%\n", pct))
# Written to the working directory as cobertura.xml regardless of `path`.
covr::to_cobertura(coverage)

if (nzchar(github_output)) {
  cat(sprintf("percent=%.10g\n", pct), file = github_output, append = TRUE)
}

step_summary <- Sys.getenv("GITHUB_STEP_SUMMARY", "")
if (nzchar(step_summary)) {
  cat(
    sprintf(
      "Package coverage: %.2f%% (type: %s)\n",
      pct,
      paste(type, collapse = ", ")
    ),
    file = step_summary,
    append = TRUE
  )
}
