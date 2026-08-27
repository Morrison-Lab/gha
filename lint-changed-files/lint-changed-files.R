#!/usr/bin/env Rscript

# Lint R files at one of three scopes (changed-files / package / project).
#
# Environment:
#   LINT_SCOPE         changed-files (default), package, or project
#   LINT_PATH          directory to lint (package root or project root)
#   LINT_LINTER_FILE   optional path passed to options(lintr.linter_file)
#   LINT_FAIL          "false" to warn instead of failing (default: fail)
#   GITHUB_REPOSITORY  owner/repo (changed-files only)
#   PR_NUMBER          pull request number (changed-files only)
#   GITHUB_PAT         token for gh::gh (changed-files only)
#   GITHUB_ACTION_PATH composite action path (to source lint-r-scope.R)

action_path <- Sys.getenv("GITHUB_ACTION_PATH")
if (nzchar(action_path)) {
  source(file.path(action_path, "lint-r-scope.R"))
} else {
  source("lint-r-scope.R")
}

main <- function() {
  scope <- Sys.getenv("LINT_SCOPE", "changed-files")
  path <- Sys.getenv("LINT_PATH", ".")
  linter_file <- Sys.getenv("LINT_LINTER_FILE", "")
  fail <- !identical(tolower(Sys.getenv("LINT_FAIL", "true")), "false")

  validate_scope(scope)

  pr_files <- NULL
  if (identical(scope, "changed-files")) {
    repo <- Sys.getenv("GITHUB_REPOSITORY")
    pr <- Sys.getenv("PR_NUMBER")
    if (!nzchar(repo) || !nzchar(pr)) {
      stop(
        "scope=changed-files requires a pull_request event ",
        "(GITHUB_REPOSITORY and PR_NUMBER must both be set).",
        call. = FALSE
      )
    }
    # .limit = Inf: the r-lib example and win's copy omit this, so a PR that
    # changes more files than one GitHub API page silently under-lints.
    pr_files <- gh::gh(
      sprintf("GET /repos/%s/pulls/%s/files", repo, pr),
      .limit = Inf
    )
  }

  lints <- lint_with_scope(
    scope,
    path,
    pr_files = pr_files,
    linter_file = linter_file
  )

  if (length(lints) == 0) {
    if (identical(scope, "changed-files")) {
      cat("No lints on changed files.\n")
    } else {
      cat("No lints.\n")
    }
    quit(status = 0)
  }

  print(lints)
  if (fail) {
    quit(status = 1)
  }
  cat("\nLINT_FAIL=false: reporting lints as warnings only.\n")
  quit(status = 0)
}

if (sys.nframe() == 0L) {
  main()
}
