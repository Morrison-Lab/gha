#!/usr/bin/env Rscript
# Offline unit tests for check-extra.R. Run via
#   bash check-extra/tests/test-check-extra.sh
# or directly with Rscript once purrr/withr/fs/cli/pkgload are installed.

sourced <- FALSE
candidates <- c(
  file.path("..", "check-extra.R"),
  "check-extra/check-extra.R",
  "check-extra.R"
)
for (p in candidates) {
  if (file.exists(p)) {
    source(p)
    sourced <- TRUE
    break
  }
}
if (!sourced) {
  stop("could not locate check-extra.R")
}

failures <- 0L

check <- function(label, actual, expected) {
  if (!identical(actual, expected)) {
    failures <<- failures + 1L
    cat(sprintf(
      "FAIL: %s\n  expected: %s\n  actual:   %s\n",
      label,
      paste(deparse(expected), collapse = " "),
      paste(deparse(actual), collapse = " ")
    ))
    return(invisible())
  }
  cat(sprintf("ok - %s\n", label))
}

check_error <- function(label, expr, pattern = NULL, error_pattern = NULL) {
  # Match the pattern against the condition message AND anything the
  # expression printed. testthat reports which warning fired through its
  # reporter (stdout), while the condition it raises says only
  # "Test failures." -- so a pattern naming the warning text could never
  # match conditionMessage() alone, however the chain is walked. Messages are
  # collected too, since cli::cli_inform() writes conditions rather than
  # stdout.
  msgs <- character()
  err <- NULL
  printed <- capture.output(
    withCallingHandlers(
      err <- tryCatch({
        force(expr)
        NULL
      }, error = function(e) e),
      message = function(m) {
        msgs <<- c(msgs, conditionMessage(m))
        invokeRestart("muffleMessage")
      }
    )
  )
  if (is.null(err)) {
    failures <<- failures + 1L
    cat(sprintf("FAIL: %s (expected an error, none raised)\n", label))
    return(invisible())
  }
  # `error_pattern` is checked against the CONDITION alone. Widening `pattern`
  # to the printed output costs something real: an unrelated error passes so
  # long as the text appears somewhere, since nothing ties the two together
  # any more. Verified -- an expression that prints the pattern and then stops
  # for another reason passes on `pattern` alone. Call sites that care assert
  # the condition separately, which restores the link without requiring detail
  # the condition does not carry.
  if (!is.null(error_pattern) &&
      !grepl(error_pattern, conditionMessage(err), perl = TRUE)) {
    failures <<- failures + 1L
    cat(sprintf(
      "FAIL: %s (condition did not match /%s/): %s\n",
      label, error_pattern, conditionMessage(err)
    ))
    return(invisible())
  }
  haystack <- paste(c(conditionMessage(err), printed, msgs), collapse = "\n")
  if (!is.null(pattern) && !grepl(pattern, haystack, perl = TRUE)) {
    failures <<- failures + 1L
    cat(sprintf(
      "FAIL: %s (error did not match /%s/): %s\n",
      label, pattern, haystack
    ))
    return(invisible())
  }
  cat(sprintf("ok - %s\n", label))
}

check_silent_ok <- function(label, expr, must_match = NULL) {
  # The functions under test report a skip with cli::cli_inform(), which is a
  # CONDITION written to stderr -- capture.output() only takes stdout, so it
  # returned "" here and every must_match failed while the text leaked to the
  # console. Collect messages alongside stdout, and muffle them so a passing
  # run stays quiet.
  msgs <- character()
  stdout_lines <- capture.output(
    withCallingHandlers(
      force(expr),
      message = function(m) {
        msgs <<- c(msgs, conditionMessage(m))
        invokeRestart("muffleMessage")
      }
    )
  )
  out <- paste(c(stdout_lines, msgs), collapse = "\n")
  if (!is.null(must_match) && !grepl(must_match, out, perl = TRUE)) {
    failures <<- failures + 1L
    cat(sprintf(
      "FAIL: %s (output did not match /%s/):\n%s\n",
      label, must_match, out
    ))
    return(invisible())
  }
  cat(sprintf("ok - %s\n", label))
}

# --- parse_flag is fail-closed --------------------------------------------
check("parse_flag: empty uses default true", parse_flag(""), TRUE)
check("parse_flag: false opts out", parse_flag("false"), FALSE)
check("parse_flag: FALSE opts out", parse_flag("FALSE"), FALSE)
check("parse_flag: padded false opts out", parse_flag(" false "), FALSE)
check("parse_flag: true stays on", parse_flag("true"), TRUE)
check("parse_flag: typo stays on", parse_flag("yes"), TRUE)
check("parse_flag: empty with default false", parse_flag("", default = FALSE), FALSE)

# --- unknown check name is an error ---------------------------------------
check_error(
  "unknown check name",
  run_check("not-a-check", pkg_path = tempdir()),
  pattern = "Unknown check"
)

empty_pkg <- tempfile("extra-empty-")
dir.create(empty_pkg)

# --- dedicated jobs fail closed when their surface is missing --------------
check_error(
  "missing README.Rmd fails the README check",
  run_check("readme", pkg_path = empty_pkg, check_readme_freshness = FALSE),
  pattern = "No README\\.Rmd"
)
check_error(
  "missing tests/testthat fails random-order",
  withr::with_dir(empty_pkg, run_random_test_order()),
  pattern = "No tests/testthat directory"
)

# --- missing surfaces of the combined warnings job skip rather than fail ---
check_silent_ok(
  "missing tests/testthat skips warnings sweep",
  withr::with_dir(empty_pkg, run_tests_warn2()),
  must_match = "No tests/testthat directory"
)
check_silent_ok(
  "missing vignettes/ skips vignette render",
  withr::with_dir(empty_pkg, run_vignettes_warn2()),
  must_match = "No vignettes/ directory"
)

# --- freshness: dirty README.md fails; clean passes ------------------------
fresh_repo <- tempfile("extra-fresh-")
dir.create(fresh_repo)
git <- function(...) {
  # system2() pastes args into one command line WITHOUT quoting, so
  # `-m "initial README"` reached git as `-m initial README`: message
  # "initial", pathspec "README". The commit then failed, README.md stayed
  # uncommitted, and the freshness check reported a dirty tree. Quoting here
  # rather than at the call site also covers fresh_repo, a tempfile path.
  # invisible(): every call site is a bare statement, and stdout = TRUE makes
  # a silent git command return character(0), which R then auto-prints. That
  # put five stray "character(0)" lines in the CI log for no reason.
  invisible(
    system2("git", shQuote(c("-C", fresh_repo, ...)), stdout = TRUE, stderr = TRUE)
  )
}
git("init", "-q")
git("config", "user.email", "fixture@example.com")
git("config", "user.name", "Fixture")
writeLines("# extrafixture\n", file.path(fresh_repo, "README.md"))
git("add", "README.md")
git("commit", "-q", "-m", "initial README")

check_silent_ok(
  "clean README.md passes freshness",
  withr::with_dir(fresh_repo, check_readme_freshness())
)

writeLines("# stale\n", file.path(fresh_repo, "README.md"))
check_error(
  "dirty README.md fails freshness",
  withr::with_dir(fresh_repo, check_readme_freshness()),
  pattern = "README\\.md is not clean"
)

# Untracked README.md is also a freshness failure: git diff --exit-code
# would miss it, which is why the check reads porcelain status.
untracked_repo <- tempfile("extra-untracked-")
dir.create(untracked_repo)
system2("git", c("-C", untracked_repo, "init", "-q"))
system2(
  "git",
  c("-C", untracked_repo, "config", "user.email", "fixture@example.com")
)
system2("git", c("-C", untracked_repo, "config", "user.name", "Fixture"))
# Need at least one commit so git status is well-defined on older git.
writeLines("ok\n", file.path(untracked_repo, "KEEP"))
system2("git", c("-C", untracked_repo, "add", "KEEP"))
system2("git", c("-C", untracked_repo, "commit", "-q", "-m", "keep"))
writeLines("# untracked\n", file.path(untracked_repo, "README.md"))
check_error(
  "untracked README.md fails freshness",
  withr::with_dir(untracked_repo, check_readme_freshness()),
  pattern = "README\\.md is not clean"
)

empty_tests <- tempfile("extra-empty-tests-")
dir.create(file.path(empty_tests, "tests", "testthat"), recursive = TRUE)
check_error(
  "empty tests/testthat fails random-order",
  withr::with_dir(empty_tests, run_random_test_order()),
  pattern = "No testthat scripts"
)

check_error(
  "main() reads CHECK from the environment",
  {
    withr::local_envvar(c(
      CHECK = "not-a-check",
      PKG_PATH = ".",
      CHECK_README_FRESHNESS = "true"
    ))
    main(character())
  },
  pattern = "Unknown check"
)

if (
  requireNamespace("pkgload", quietly = TRUE) &&
    requireNamespace("testthat", quietly = TRUE)
) {
  warn_pkg <- tempfile("extra-warn-test-")
  dir.create(file.path(warn_pkg, "R"), recursive = TRUE)
  dir.create(file.path(warn_pkg, "tests", "testthat"), recursive = TRUE)
  writeLines(
    c(
      "Package: warntest",
      "Title: Warn In Test",
      "Version: 0.0.1",
      "Author: Fixture",
      "Maintainer: Fixture <fixture@example.com>",
      "Description: Fixture whose tests warn.",
      "License: MIT",
      "Encoding: UTF-8"
    ),
    file.path(warn_pkg, "DESCRIPTION")
  )
  writeLines("export(add)", file.path(warn_pkg, "NAMESPACE"))
  writeLines("add <- function(x, y) x + y\n", file.path(warn_pkg, "R", "add.R"))
  writeLines(
    "test_that('this test warns', {\n  warning('boom from extrafixture test')\n  expect_equal(1 + 1, 2)\n})\n",
    file.path(warn_pkg, "tests", "testthat", "test-warn.R")
  )
  check_error(
    "warning in a test file fails the warnings sweep",
    withr::with_dir(warn_pkg, run_tests_warn2()),
    pattern = "boom from extrafixture test|converted from warning",
    error_pattern = "Test failures"
  )
  unlink(warn_pkg, recursive = TRUE)
}

unlink(empty_pkg, recursive = TRUE)
unlink(fresh_repo, recursive = TRUE)
unlink(untracked_repo, recursive = TRUE)
unlink(empty_tests, recursive = TRUE)

if (failures > 0L) {
  stop(sprintf("%d failure(s)", failures), call. = FALSE)
}
cat("All check-extra R tests passed.\n")
