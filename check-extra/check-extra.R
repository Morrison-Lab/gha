#!/usr/bin/env Rscript
# Extra R-package checks adapted from IndrajeetPatil/workflows
# check-extra.yaml (MIT):
# https://github.com/IndrajeetPatil/workflows
#
# Three independent checks, selected by CHECK:
#   warnings      -- examples, tests, and vignettes under options(warn = 2L)
#   random-order  -- testthat with shuffle=TRUE and a logged seed
#   readme        -- render README.Rmd under warn=2, optionally require a
#                    clean README.md afterwards
#
# Sourced by tests/test-check-extra.R (sys.nframe() > 0); run as a script
# from the composite (sys.nframe() == 0).

VALID_CHECKS <- c("warnings", "random-order", "readme")

parse_flag <- function(x, default = TRUE) {
  x <- tolower(trimws(as.character(x)))
  if (!nzchar(x)) {
    return(default)
  }
  # Fail-closed: only an explicit false opts out, so a typo cannot quietly
  # drop the freshness gate. Same shape as check-junk-files' fail input.
  if (x %in% c("false", "0", "no")) {
    return(FALSE)
  }
  TRUE
}

require_pkgs <- function(pkgs) {
  missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing)) {
    stop(
      "Required package(s) not installed: ",
      paste(missing, collapse = ", "),
      call. = FALSE
    )
  }
}

run_examples_warn2 <- function() {
  # devtools::run_examples(fresh = TRUE) uses callr::r() and does not
  # inherit parent options, so options(warn = 2L) around that call would
  # not apply to the examples. Drive the fresh session ourselves, set
  # warn=2 inside it, then run_examples(fresh = FALSE) there. Isolation
  # matches fresh=TRUE; the option actually reaches the examples.
  require_pkgs(c("callr", "devtools"))
  pkg_path <- normalizePath(".", winslash = "/", mustWork = TRUE)
  callr::r(
    function(path) {
      options(warn = 2L, crayon.enabled = TRUE)
      devtools::run_examples(
        pkg = path,
        fresh = FALSE,
        document = FALSE,
        run_dontrun = TRUE,
        run_donttest = TRUE
      )
    },
    args = list(path = pkg_path),
    show = TRUE,
    spinner = FALSE,
    stderr = "2>&1"
  )
  invisible()
}

run_tests_warn2 <- function() {
  # Parallel testthat does not honor a global warn option
  # (r-lib/testthat#1912), so a single options(warn = 2L) around
  # testthat::test_local() would miss warnings in worker processes.
  # Load the package first (outside warn=2, so load_all's own messages
  # are not the thing under test), then run each test file inside
  # withr::local_options(list(warn = 2L)).
  require_pkgs(c("pkgload", "purrr", "testthat", "withr", "cli"))
  test_dir <- "tests/testthat"
  if (!dir.exists(test_dir)) {
    cli::cli_inform(
      "No tests/testthat directory; skipping the warnings-as-errors test sweep."
    )
    return(invisible())
  }
  paths <- testthat::find_test_scripts(test_dir)
  if (!length(paths)) {
    cli::cli_inform(
      "No testthat scripts found; skipping the warnings-as-errors test sweep."
    )
    return(invisible())
  }
  withr::local_envvar(list(TESTTHAT_PARALLEL = "FALSE"))
  pkgload::load_all(".")
  test_with_warning_as_error <- function(path) {
    withr::local_options(list(warn = 2L, crayon.enabled = TRUE))
    testthat::test_file(
      path,
      stop_on_failure = TRUE,
      stop_on_warning = TRUE
    )
  }
  purrr::walk(paths, test_with_warning_as_error)
  invisible()
}

run_vignettes_warn2 <- function() {
  require_pkgs(c("fs", "purrr", "rmarkdown", "withr", "cli"))
  if (!dir.exists("vignettes")) {
    cli::cli_inform(
      "No vignettes/ directory; skipping the warnings-as-errors vignette render."
    )
    return(invisible())
  }
  # Issue #335 names this glob exactly. .qmd vignettes are out of scope;
  # they need Quarto, which this check does not install.
  vignettes <- fs::dir_ls("vignettes/", glob = "*.Rmd", recurse = TRUE)
  if (!length(vignettes)) {
    cli::cli_inform(
      "No vignette .Rmd files; skipping the warnings-as-errors vignette render."
    )
    return(invisible())
  }
  withr::local_options(list(warn = 2L, crayon.enabled = TRUE))
  purrr::walk(vignettes, rmarkdown::render)
  invisible()
}

run_warnings_as_errors <- function() {
  run_examples_warn2()
  run_tests_warn2()
  run_vignettes_warn2()
  invisible()
}

run_random_test_order <- function() {
  # testthat::test_dir("tests") would also match tests/testthat.R (the
  # helper whose name starts with "test"), so we point at tests/testthat,
  # the directory testthat::test_local() uses. shuffle=TRUE is the whole
  # point of this check; TESTTHAT_PARALLEL=FALSE because shuffling is
  # meaningless if tests run in parallel anyway.
  require_pkgs(c("pkgload", "testthat", "withr", "cli"))
  test_dir <- "tests/testthat"
  if (!dir.exists(test_dir)) {
    cli::cli_inform(
      "No tests/testthat directory; skipping the random-order check."
    )
    return(invisible())
  }
  withr::local_options(list(crayon.enabled = TRUE))
  withr::local_envvar(list(TESTTHAT_PARALLEL = "FALSE"))
  seed <- sample.int(1e6, 1L)
  cli::cli_inform("Chosen seed for the current test run: {seed}")
  set.seed(seed)
  pkgload::load_all(".")
  testthat::test_dir(
    test_dir,
    shuffle = TRUE,
    stop_on_failure = TRUE
  )
  invisible()
}

check_readme_freshness <- function() {
  # Fail when README.md is modified or untracked after the render.
  # git diff --exit-code alone misses an untracked README.md (a package
  # that has README.Rmd but never committed the knitted README.md).
  status <- system2(
    "git",
    c("status", "--porcelain", "--", "README.md"),
    stdout = TRUE,
    stderr = TRUE
  )
  status_code <- attr(status, "status")
  if (!is.null(status_code) && status_code != 0L) {
    stop(
      "git status failed while checking README.md freshness:\n",
      paste(status, collapse = "\n"),
      call. = FALSE
    )
  }
  if (length(status) && any(nzchar(status))) {
    diff <- system2(
      "git",
      c("diff", "--", "README.md"),
      stdout = TRUE,
      stderr = TRUE
    )
    stop(
      "README.md is not clean after rendering README.Rmd. ",
      "Re-render and commit the result.\n",
      paste(c(status, diff), collapse = "\n"),
      call. = FALSE
    )
  }
  invisible()
}

run_readme_check <- function(check_freshness = TRUE) {
  require_pkgs(c("rmarkdown", "withr", "cli"))
  if (!file.exists("README.Rmd")) {
    cli::cli_inform("No README.Rmd; skipping the README render check.")
    return(invisible())
  }
  withr::local_options(list(warn = 2L, crayon.enabled = TRUE))
  rmarkdown::render("README.Rmd")
  if (isTRUE(check_freshness)) {
    check_readme_freshness()
  }
  invisible()
}

run_check <- function(check, pkg_path = ".", check_readme_freshness = TRUE) {
  if (!check %in% VALID_CHECKS) {
    stop(
      "Unknown check ", sQuote(check),
      ". Expected one of: ", paste(VALID_CHECKS, collapse = ", "),
      call. = FALSE
    )
  }
  pkg_path <- normalizePath(pkg_path, winslash = "/", mustWork = TRUE)
  require_pkgs("withr")
  withr::with_dir(pkg_path, {
    switch(
      check,
      warnings = run_warnings_as_errors(),
      `random-order` = run_random_test_order(),
      readme = run_readme_check(check_readme_freshness),
      stop("unhandled check: ", check, call. = FALSE)
    )
  })
  invisible()
}

main <- function(args = commandArgs(trailingOnly = TRUE)) {
  check <- Sys.getenv("CHECK", unset = "")
  pkg_path <- Sys.getenv("PKG_PATH", unset = ".")
  freshness <- parse_flag(
    Sys.getenv("CHECK_README_FRESHNESS", unset = "true"),
    default = TRUE
  )
  if (length(args) >= 1L && nzchar(args[[1L]])) {
    check <- args[[1L]]
  }
  if (length(args) >= 2L && nzchar(args[[2L]])) {
    pkg_path <- args[[2L]]
  }
  if (length(args) >= 3L && nzchar(args[[3L]])) {
    freshness <- parse_flag(args[[3L]], default = TRUE)
  }
  if (!nzchar(check)) {
    stop(
      "CHECK is empty. Pass warnings, random-order, or readme.",
      call. = FALSE
    )
  }
  run_check(check, pkg_path = pkg_path, check_readme_freshness = freshness)
}

if (sys.nframe() == 0L) {
  main()
}
