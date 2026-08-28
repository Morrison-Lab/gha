#!/usr/bin/env Rscript

# Offline unit tests for lint-r-scope.R. Run with:
#   Rscript lint-changed-files/tests/test-lint-r-scope.R
# Helper tests are base R. lintr integration tests run when lintr is installed
# (the lint-changed-files-tests selftest job installs it from CRAN).

sourced <- FALSE
candidates <- c(
  "lint-changed-files/lint-r-scope.R",
  "../lint-r-scope.R",
  "lint-r-scope.R"
)
for (p in candidates) {
  if (file.exists(p)) {
    source(p)
    sourced <- TRUE
    break
  }
}
if (!sourced) {
  stop("could not locate lint-r-scope.R")
}

sourced <- FALSE
candidates <- c(
  ".github/workflows/scripts/tests/r-test-helpers.R",
  "../../.github/workflows/scripts/tests/r-test-helpers.R",
  "r-test-helpers.R"
)
for (p in candidates) {
  if (file.exists(p)) {
    source(p)
    sourced <- TRUE
    break
  }
}
if (!sourced) stop("could not locate r-test-helpers.R")

# --- validate_scope -------------------------------------------------------

check("validate_scope accepts changed-files", validate_scope("changed-files"), "changed-files")
check("validate_scope accepts package", validate_scope("package"), "package")
check("validate_scope accepts project", validate_scope("project"), "project")
check_error(
  "validate_scope rejects an unknown value",
  validate_scope("lines"),
  "Unknown scope",
  fixed = TRUE
)
check_error(
  "validate_scope rejects a changed-lines alias",
  validate_scope("changed-lines"),
  "Unknown scope",
  fixed = TRUE
)

# --- rel_to_path ----------------------------------------------------------

check(
  "rel_to_path drops files outside path",
  rel_to_path(c("pkg/R/a.R", "other.R", "pkg/tests/t.R"), "pkg"),
  c("R/a.R", "tests/t.R")
)
check(
  "rel_to_path with '.' keeps repo-relative paths",
  rel_to_path(c("R/a.R", "other.R"), "."),
  c("R/a.R", "other.R")
)
check(
  "rel_to_path with empty path keeps repo-relative paths",
  rel_to_path(c("R/a.R"), ""),
  "R/a.R"
)
check(
  "rel_to_path strips a trailing slash on path",
  rel_to_path("pkg/R/a.R", "pkg/"),
  "R/a.R"
)

# --- pr_changed_paths -----------------------------------------------------

files <- list(
  list(filename = "R/a.R", status = "modified"),
  list(filename = "R/gone.R", status = "removed"),
  list(filename = "R/new.R", status = "added"),
  list(filename = "R/renamed.R", status = "renamed")
)
check(
  "pr_changed_paths skips removed files and keeps the new name of a rename",
  pr_changed_paths(files),
  c("R/a.R", "R/new.R", "R/renamed.R")
)

many <- lapply(seq_len(101L), function(i) {
  list(filename = sprintf("R/f%03d.R", i), status = "modified")
})
check(
  "pr_changed_paths does not drop list elements (101 files)",
  length(pr_changed_paths(many)),
  101L
)

# Pagination lives in lint-changed-files.R's gh::gh(.limit = Inf) call,
# not in pr_changed_paths. Walking 101 files does not pin that argument.
script_candidates <- c(
  "lint-changed-files/lint-changed-files.R",
  "../lint-changed-files.R",
  "lint-changed-files.R"
)
script_path <- NULL
for (p in script_candidates) {
  if (file.exists(p)) {
    script_path <- p
    break
  }
}
if (is.null(script_path)) {
  stop("could not locate lint-changed-files.R")
}
script_code <- readLines(script_path)
script_code <- script_code[!grepl("^\\s*#", script_code)]
check(
  "lint-changed-files.R passes .limit = Inf to gh::gh (not only a comment)",
  any(grepl(".limit = Inf", script_code, fixed = TRUE)),
  TRUE
)

# --- list_project_files / exclusions --------------------------------------

tmp <- tempfile("lint-r-scope-")
dir.create(tmp)
dir.create(file.path(tmp, "R"))
dir.create(file.path(tmp, ".git", "objects"), recursive = TRUE)
writeLines("x <- 1", file.path(tmp, "R", "ok.R"))
writeLines("linters <- list()", file.path(tmp, ".lintr.R"))
writeLines("blob", file.path(tmp, ".git", "objects", "ab"))
on.exit(unlink(tmp, recursive = TRUE), add = TRUE)

listed <- list_project_files(tmp)
check("list_project_files includes a regular R file", "R/ok.R" %in% listed, TRUE)
check(
  "list_project_files includes .lintr.R (all.files = TRUE)",
  ".lintr.R" %in% listed,
  TRUE
)
check(
  "list_project_files drops .git contents",
  any(startsWith(listed, ".git/")),
  FALSE
)

tmp_gitfile <- tempfile("lint-r-gitfile-")
dir.create(tmp_gitfile)
writeLines("not a dir", file.path(tmp_gitfile, ".git"))
writeLines("x <- 1", file.path(tmp_gitfile, "ok.R"))
on.exit(unlink(tmp_gitfile, recursive = TRUE), add = TRUE)
check(
  "list_project_files drops a file named .git",
  !(".git" %in% list_project_files(tmp_gitfile)),
  TRUE
)

ex <- changed_file_exclusions(c(".lintr.R", "R/ok.R", "R/dirty.R"), "R/ok.R")
check(
  "unchanged .lintr.R is excluded so it is not linted on every PR",
  ".lintr.R" %in% unlist(ex),
  TRUE
)
check(
  "unchanged dirty file is excluded",
  "R/dirty.R" %in% unlist(ex),
  TRUE
)
check(
  "the changed file is not excluded",
  "R/ok.R" %in% unlist(ex),
  FALSE
)

# --- apply_linter_file ----------------------------------------------------

old_opt <- getOption("lintr.linter_file")
on.exit(options(lintr.linter_file = old_opt), add = TRUE)
options(lintr.linter_file = NULL)
apply_linter_file("")
check(
  "empty linter-file leaves the option unset",
  getOption("lintr.linter_file"),
  NULL
)
apply_linter_file(".lintr.R")
check(
  "non-empty linter-file sets options(lintr.linter_file)",
  getOption("lintr.linter_file"),
  ".lintr.R"
)
options(lintr.linter_file = old_opt)

# --- changed-files with no matching files does not need lintr -------------

lints <- lint_with_scope(
  "changed-files",
  path = tmp,
  pr_files = list(list(filename = "README.md", status = "modified"))
)
check(
  "changed-files with no files under path returns empty lints",
  length(lints),
  0L
)
check_error(
  "changed-files without pr_files errors",
  lint_with_scope("changed-files", path = tmp),
  "pull request's file list",
  fixed = TRUE
)
check_error(
  "package scope without DESCRIPTION errors clearly",
  lint_with_scope("package", path = tmp),
  "requires a DESCRIPTION",
  fixed = TRUE
)

# --- defaults agreement (action.yml vs reusable workflow) -----------------

read_input_default <- function(path, input_name) {
  lines <- readLines(path)
  # Find the input key at either composite (`  name:`) or workflow
  # (`      name:`) indentation, then the next `default:` under it.
  # Nested keys (`description:`, `type:`) are deeper, so they must not
  # count as the next sibling input -- that would make the default-search
  # block empty (gha#303).
  key <- grep(sprintf("^[ \t]+%s:", input_name), lines)
  if (length(key) == 0L) {
    stop(sprintf("%s: no input named %s", path, input_name))
  }
  indent <- nchar(sub("[^ \t].*$", "", lines[key[[1]]]))
  rest <- lines[(key[[1]] + 1L):length(lines)]
  rest_indent <- nchar(sub("[^ \t].*$", "", rest))
  sibling <- which(
    grepl("^[ \t]+[A-Za-z0-9_-]+:", rest) & rest_indent <= indent
  )
  block <- if (length(sibling)) rest[seq_len(sibling[[1]] - 1L)] else rest
  def <- grep("^[ \t]+default:", block, value = TRUE)
  if (length(def) == 0L) {
    stop(sprintf("%s: %s has no default", path, input_name))
  }
  val <- sub("^[ \t]+default:[ \t]*", "", def[[1]])
  gsub("^['\"]|['\"]$", "", val)
}

action_yml <- NULL
workflow_yml <- NULL
yml_candidates <- list(
  c("lint-changed-files/action.yml", ".github/workflows/lint-changed-files.yml"),
  c("../action.yml", "../../.github/workflows/lint-changed-files.yml"),
  c("action.yml", "../.github/workflows/lint-changed-files.yml")
)
for (pair in yml_candidates) {
  if (file.exists(pair[[1]]) && file.exists(pair[[2]])) {
    action_yml <- pair[[1]]
    workflow_yml <- pair[[2]]
    break
  }
}
if (is.null(action_yml)) {
  stop("could not locate action.yml and lint-changed-files.yml")
}

for (input_name in c(
  "scope",
  "path",
  "linter-file",
  "install-quarto",
  "use-renv",
  "renv-cache-version",
  "apt-packages",
  "extra-packages",
  "install-package",
  "fail"
)) {
  a <- read_input_default(action_yml, input_name)
  w <- read_input_default(workflow_yml, input_name)
  check(
    sprintf("default for %s agrees between action.yml and the reusable workflow", input_name),
    a,
    w
  )
}

# --- lintr integration (skipped if lintr is not installed) ----------------

if (!requireNamespace("lintr", quietly = TRUE)) {
  cat("skip lintr integration tests (lintr not installed)\n")
  cat("\nAll lint-r-scope helper tests passed.\n")
  quit(status = 0)
}

write_lintr_config <- function(dir) {
  writeLines(
    c(
      "linters <- list(",
      "  assignment_linter = lintr::assignment_linter()",
      ")"
    ),
    file.path(dir, ".lintr.R")
  )
}

# GitHub "list PR files" filenames are repo-root-relative. rel_to_path()
# prefix-matches those against `path`, so changed-files tests must run
# with the fixture as cwd and path = "." / "pkg" -- an absolute tempfile
# path never matches "dirty.R" and every case would return empty lints
# before lintr ran.
with_dir <- function(dir, expr) {
  old <- setwd(dir)
  on.exit(setwd(old), add = TRUE)
  force(expr)
}

proj <- tempfile("lint-r-proj-")
dir.create(proj)
write_lintr_config(proj)
writeLines("x <- 1", file.path(proj, "clean.R"))
writeLines("x = 1", file.path(proj, "dirty.R"))
on.exit(unlink(proj, recursive = TRUE), add = TRUE)

proj_lints <- lint_with_scope("project", path = proj)
proj_files <- vapply(proj_lints, function(l) l$filename, character(1))
check("project scope reports the dirty file", any(grepl("dirty\\.R$", proj_files)), TRUE)
check("project scope reports no lint on the clean file", !any(grepl("clean\\.R$", proj_files)), TRUE)

changed_only <- with_dir(proj, {
  lint_with_scope(
    "changed-files",
    path = ".",
    pr_files = list(list(filename = "clean.R", status = "modified"))
  )
})
check(
  "changed-files excludes an unchanged dirty file (the r-lib exclusion pattern)",
  length(changed_only),
  0L
)

changed_dirty <- with_dir(proj, {
  lint_with_scope(
    "changed-files",
    path = ".",
    pr_files = list(list(filename = "dirty.R", status = "modified"))
  )
})
check(
  "changed-files reports a lint on a changed dirty file",
  length(changed_dirty) > 0L,
  TRUE
)

# Package with DESCRIPTION: lint_package, so a stray root .R file is not linted
# even when it is in the changed-file set (rpt uses lint_package; qwt/win use
# lint_dir because they have no DESCRIPTION). Nested under a fake repo root
# so path = "pkg" plus GitHub-shaped "pkg/..." filenames exercise rel_to_path.
repo <- tempfile("lint-r-repo-")
dir.create(repo)
pkg <- file.path(repo, "pkg")
dir.create(pkg)
dir.create(file.path(pkg, "R"))
writeLines(
  c(
    "Package: lintfixture",
    "Title: Lint Selftest Fixture",
    "Version: 0.0.1",
    "License: MIT",
    "Encoding: UTF-8"
  ),
  file.path(pkg, "DESCRIPTION")
)
write_lintr_config(pkg)
writeLines("x <- 1", file.path(pkg, "R", "ok.R"))
writeLines("x = 1", file.path(pkg, "R", "bad.R"))
writeLines("x = 1", file.path(pkg, "stray.R"))
on.exit(unlink(repo, recursive = TRUE), add = TRUE)

pkg_changed_stray <- with_dir(repo, {
  lint_with_scope(
    "changed-files",
    path = "pkg",
    pr_files = list(list(filename = "pkg/stray.R", status = "modified"))
  )
})
check(
  "changed-files on a package uses lint_package, so a root stray.R is not linted",
  length(pkg_changed_stray),
  0L
)

pkg_changed_bad <- with_dir(repo, {
  lint_with_scope(
    "changed-files",
    path = "pkg",
    pr_files = list(list(filename = "pkg/R/bad.R", status = "modified"))
  )
})
check(
  "changed-files with path='pkg' reports a lint on pkg/R/bad.R",
  length(pkg_changed_bad) > 0L,
  TRUE
)

no_desc <- tempfile("lint-r-nodesc-")
dir.create(no_desc)
write_lintr_config(no_desc)
writeLines("x = 1", file.path(no_desc, "stray.R"))
on.exit(unlink(no_desc, recursive = TRUE), add = TRUE)
proj_stray <- with_dir(no_desc, {
  lint_with_scope(
    "changed-files",
    path = ".",
    pr_files = list(list(filename = "stray.R", status = "modified"))
  )
})
check(
  "changed-files without DESCRIPTION uses lint_dir, so stray.R is linted",
  length(proj_stray) > 0L,
  TRUE
)

pkg_clean <- lint_with_scope("package", path = pkg)
check(
  "package scope on a package with a dirty R/ file reports lints",
  length(pkg_clean) > 0L,
  TRUE
)

pkg_ok_only <- tempfile("lint-r-pkgok-")
dir.create(pkg_ok_only)
dir.create(file.path(pkg_ok_only, "R"))
writeLines(
  c(
    "Package: lintfixtureok",
    "Title: Lint Selftest Fixture",
    "Version: 0.0.1",
    "License: MIT",
    "Encoding: UTF-8"
  ),
  file.path(pkg_ok_only, "DESCRIPTION")
)
write_lintr_config(pkg_ok_only)
writeLines("x <- 1", file.path(pkg_ok_only, "R", "ok.R"))
on.exit(unlink(pkg_ok_only, recursive = TRUE), add = TRUE)
check(
  "package scope on a clean package reports no lints",
  length(lint_with_scope("package", path = pkg_ok_only)),
  0L
)

cat("\nAll lint-r-scope tests passed.\n")
