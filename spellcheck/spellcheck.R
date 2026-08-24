#!/usr/bin/env Rscript
# Spellcheck an R package with {spelling}, supporting exclusions and fail input.
# Avoids r-spellcheck-action's file deletion bug and 256-word exit code modulo bug (gha#556, gha#560).

suppressPackageStartupMessages({
  if (!requireNamespace("spelling", quietly = TRUE)) {
    stop("Package 'spelling' is not installed.")
  }
})

args <- commandArgs(trailingOnly = TRUE)
pkg_path <- Sys.getenv("INPUT_PATH", ".")
if (length(args) >= 1 && nzchar(args[1])) {
  pkg_path <- args[1]
}

raw_exclude <- Sys.getenv("INPUT_EXCLUDE", "")
if (length(args) >= 2) {
  raw_exclude <- args[2]
}

fail_input <- Sys.getenv("INPUT_FAIL", "true")
if (length(args) >= 3) {
  fail_input <- args[3]
}
should_fail <- tolower(trimws(fail_input)) %in% c("true", "1", "yes")

# Handle exclusions by temporarily moving matching files out of the package root
temp_backup_dir <- tempfile("spellcheck_exclude_")
excluded_files <- character()

if (nzchar(raw_exclude)) {
  patterns <- trimws(strsplit(raw_exclude, ",")[[1]])
  patterns <- patterns[nzchar(patterns)]

  for (pat in patterns) {
    full_pat <- if (pkg_path == ".") pat else file.path(pkg_path, pat)
    matches <- Sys.glob(full_pat)
    excluded_files <- union(excluded_files, matches)
  }
}

if (length(excluded_files) > 0) {
  dir.create(temp_backup_dir, recursive = TRUE, showWarnings = FALSE)
  for (f in excluded_files) {
    if (file.exists(f)) {
      dest <- file.path(temp_backup_dir, f)
      dir.create(dirname(dest), recursive = TRUE, showWarnings = FALSE)
      file.rename(f, dest)
    }
  }
}

# Ensure restoration on exit
restore_exclusions <- function() {
  if (length(excluded_files) > 0 && dir.exists(temp_backup_dir)) {
    for (f in excluded_files) {
      dest <- file.path(temp_backup_dir, f)
      if (file.exists(dest)) {
        dir.create(dirname(f), recursive = TRUE, showWarnings = FALSE)
        file.rename(dest, f)
      }
    }
    unlink(temp_backup_dir, recursive = TRUE)
  }
}
on.exit(restore_exclusions(), add = TRUE)

# Run spell check
words <- spelling::spell_check_package(pkg = pkg_path)
n_words <- nrow(words)

if (n_words > 0) {
  cat("\n")
  print(words)
  cat("\n")

  # Format GitHub Actions annotations
  for (i in seq_len(n_words)) {
    w <- words$word[i]
    found <- paste(words$Found[i], collapse = ", ")
    cat(sprintf("::warning::Possible misspelled word '%s' in: %s\n", w, found))
  }

  msg <- sprintf("Spellcheck found %d potentially misspelled word%s.", n_words, if (n_words == 1) "" else "s")
  if (should_fail) {
    cat(sprintf("::error::%s (fail=true)\n", msg))
    quit(save = "no", status = 1, runLast = FALSE)
  } else {
    cat(sprintf("::warning::%s (fail=false, check passes with warnings)\n", msg))
    quit(save = "no", status = 0, runLast = FALSE)
  }
} else {
  cat("Spellcheck clean: 0 misspelled words found.\n")
  quit(save = "no", status = 0, runLast = FALSE)
}
