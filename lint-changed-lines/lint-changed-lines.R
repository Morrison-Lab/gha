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
if (repo == "" || pr == "") {
  stop("GITHUB_REPOSITORY and PR_NUMBER must both be set.")
}

files <- gh::gh(sprintf("GET /repos/%s/pulls/%s/files", repo, pr), .limit = Inf)

changed <- list()
for (f in files) {
  path <- f$filename
  if (!grepl("[.][Rr]$", path)) next
  if (identical(f$status, "removed")) next
  if (!file.exists(path)) next
  lines <- added_lines(f$patch)
  if (length(lines) > 0) {
    changed[[path]] <- lines
  }
}

if (length(changed) == 0) {
  cat("No changed R lines to lint.\n")
  quit(status = 0)
}

lints <- list()
for (path in names(changed)) {
  on_changed <- Filter(
    function(l) l$line_number %in% changed[[path]],
    lintr::lint(path)
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
