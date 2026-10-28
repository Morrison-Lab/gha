#!/usr/bin/env Rscript

# Lint only the lines added or modified by the current pull request.
#
# Runs lintr on each changed R file in the checked-out repository, then keeps
# only the lints whose line falls on a line this PR added or modified (parsed
# from the PR's diff hunks via the GitHub "list PR files" API). This supports
# adopting or tightening lint rules incrementally: new and edited code must
# comply, while untouched legacy code in the same file is not flagged.
#
# The repository must be checked out at the PR *head* commit (not the default
# refs/pull/N/merge ref), so on-disk line numbers match the patch's line
# numbers -- the reusable workflow pins `ref: head.sha` for this reason.
#
# Environment:
#   GITHUB_REPOSITORY  owner/repo (set automatically by GitHub Actions)
#   PR_NUMBER          the pull request number
#   GITHUB_PAT         a token for the GitHub API (gh::gh)
#   LINT_FAIL          "false" to warn instead of failing (default: fail)
#   LINT_FILE_PATTERN  regex of repo-relative paths to lint (default: R files)
#   LINT_LMS           "true" to lint with lms::default_linters(nested_calls = TRUE)
#   GITHUB_ACTION_PATH the composite action's path (to source added-lines.R)

action_path <- Sys.getenv("GITHUB_ACTION_PATH")
if (nzchar(action_path)) {
  source(file.path(action_path, "added-lines.R"))
} else {
  # Fallback for local runs: added-lines.R sits next to this script.
  source("added-lines.R")
}

repo <- Sys.getenv("GITHUB_REPOSITORY")
pr <- Sys.getenv("PR_NUMBER")
fail <- !identical(tolower(Sys.getenv("LINT_FAIL", "true")), "false")
file_pattern <- Sys.getenv("LINT_FILE_PATTERN", DEFAULT_LINT_FILE_PATTERN)
use_lms <- identical(tolower(Sys.getenv("LINT_LMS", "false")), "true")
# With lms the lab's linters (including the no-nested-calls rules) replace the
# repository's own linter list; its exclusions in .lintr.R still apply.
linters <- if (use_lms) {
  lms::default_linters(nested_calls = TRUE)
} else {
  NULL # lintr then uses the linters configured in .lintr.R
}
if (repo == "" || pr == "") {
  stop("GITHUB_REPOSITORY and PR_NUMBER must both be set.")
}

files <- gh::gh(sprintf("GET /repos/%s/pulls/%s/files", repo, pr), .limit = Inf)

changed <- list()
for (f in files) {
  path <- f$filename
  if (!is_lint_target(path, file_pattern)) next
  if (identical(f$status, "removed")) next
  if (!file.exists(path)) next
  lines <- added_lines(f$patch)
  if (length(lines) > 0) {
    changed[[path]] <- lines
  }
}

if (length(changed) == 0) {
  cat("No changed lines to lint.\n")
  quit(status = 0)
}

lints <- list()
for (path in names(changed)) {
  on_changed <- Filter(
    function(l) l$line_number %in% changed[[path]],
    lintr::lint(path, linters = linters)
  )
  lints <- c(lints, on_changed)
}

if (length(lints) == 0) {
  cat("No lints on changed lines.\n")
  quit(status = 0)
}

print(structure(lints, class = "lints"))
if (fail) {
  quit(status = 1)
}
cat("\nLINT_FAIL=false: reporting lints as warnings only.\n")
quit(status = 0)
