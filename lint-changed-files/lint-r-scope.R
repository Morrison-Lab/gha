# Helpers for lint-changed-files: choose a lintr scope and, for changed-files,
# build the exclusion list from a pull request's file list.
#
# Three scopes, matching the bespoke copies this capability replaces:
#   changed-files -- lint only files this PR changed (r-lib / win / rpt / qwt)
#   package       -- lintr::lint_package() over the whole package
#   project       -- lintr::lint_dir() over the whole project (qwt / qbt)
#
# changed-files uses lint_package() when path holds a DESCRIPTION (rpt) and
# lint_dir() otherwise (win / qwt). The exclusion list is the r-lib pattern
# (lint everything except files this PR did not change), with two bugs in the
# upstream example closed here:
#   * gh::gh(..., .limit = Inf) so files past the first API page are not
#     dropped (the r-lib / win copies omit .limit).
#   * list.files(all.files = TRUE) so an unchanged dotfile such as `.lintr.R`
#     is excluded rather than linted on every PR (qwt's all.files fix).

VALID_SCOPES <- c("changed-files", "package", "project")

validate_scope <- function(scope) {
  if (!scope %in% VALID_SCOPES) {
    stop(
      sprintf(
        "Unknown scope %s; must be one of: %s.",
        encodeString(scope, quote = "'"),
        paste(VALID_SCOPES, collapse = ", ")
      ),
      call. = FALSE
    )
  }
  invisible(scope)
}

normalize_rel_path <- function(path) {
  path <- gsub("\\\\", "/", path)
  path <- sub("^\\./", "", path)
  path <- sub("/+$", "", path)
  if (!nzchar(path) || identical(path, ".")) {
    return(".")
  }
  path
}

# Convert repo-root-relative paths (GitHub "list PR files" filenames) to paths
# relative to `path`. Files outside `path` are dropped.
rel_to_path <- function(repo_paths, path) {
  path <- normalize_rel_path(path)
  if (identical(path, ".")) {
    return(repo_paths)
  }
  prefix <- paste0(path, "/")
  inside <- startsWith(repo_paths, prefix)
  substring(repo_paths[inside], nchar(prefix) + 1L)
}

pr_changed_paths <- function(files) {
  paths <- character()
  for (f in files) {
    if (identical(f$status, "removed")) {
      next
    }
    paths <- c(paths, f$filename)
  }
  paths
}

# Files lintr would see under `path`, including dotfiles (so `.lintr.R` can
# be excluded when unchanged) but not `.git/` (list.files(all.files=TRUE)
# would otherwise dump the object store into the exclusion list).
list_project_files <- function(path) {
  path <- normalize_rel_path(path)
  files <- list.files(
    path,
    recursive = TRUE,
    all.files = TRUE,
    no.. = TRUE
  )
  files[!startsWith(files, ".git/") & files != ".git"]
}

changed_file_exclusions <- function(all_files, changed) {
  as.list(setdiff(all_files, changed))
}

has_description <- function(path) {
  file.exists(file.path(normalize_rel_path(path), "DESCRIPTION"))
}

apply_linter_file <- function(linter_file) {
  if (nzchar(linter_file)) {
    options(lintr.linter_file = linter_file)
  }
  invisible(linter_file)
}

empty_lints <- function() {
  structure(list(), class = "lints")
}

# `pr_files` is the list gh::gh() returns for GET .../pulls/{n}/files.
# Required when scope is changed-files; ignored otherwise.
lint_with_scope <- function(scope,
                            path = ".",
                            pr_files = NULL,
                            linter_file = "") {
  validate_scope(scope)
  apply_linter_file(linter_file)
  path <- normalize_rel_path(path)

  if (identical(scope, "package")) {
    if (!has_description(path)) {
      stop(
        sprintf(
          "scope=package requires a DESCRIPTION file at %s.",
          encodeString(path, quote = "'")
        ),
        call. = FALSE
      )
    }
    return(lintr::lint_package(path))
  }
  if (identical(scope, "project")) {
    return(lintr::lint_dir(path))
  }

  if (is.null(pr_files)) {
    stop(
      "scope=changed-files requires the pull request's file list.",
      call. = FALSE
    )
  }
  changed <- rel_to_path(pr_changed_paths(pr_files), path)
  if (length(changed) == 0L) {
    return(empty_lints())
  }
  exclusions <- changed_file_exclusions(list_project_files(path), changed)
  if (has_description(path)) {
    lintr::lint_package(path, exclusions = exclusions)
  } else {
    lintr::lint_dir(path, exclusions = exclusions)
  }
}
