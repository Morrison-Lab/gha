# Parse a unified-diff patch into the set of new-file line numbers it adds or
# modifies. Delegates to ghatools::added_lines (ghatools/R/added_lines.R; gha#383).

here <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
file_candidates <- c(
  file.path(here, "..", "ghatools", "R", "added_lines.R"),
  file.path(here, "..", "..", "ghatools", "R", "added_lines.R"),
  "ghatools/R/added_lines.R"
)
rpkg_file <- file_candidates[file.exists(file_candidates)][1]
if (!is.na(rpkg_file) && file.exists(rpkg_file)) {
  source(rpkg_file)
} else if (requireNamespace("ghatools", quietly = TRUE)) {
  added_lines <- ghatools::added_lines
} else {
  stop("Unable to locate ghatools package or ghatools/R/added_lines.R source file")
}


# Decide whether a changed file is one lint-changed-lines should lint.
#
# `pattern` is an extended regular expression matched against the repo-relative
# path (default: R source files only). A Quarto or R Markdown pattern such as
# `[.]([Rr]|[Rr]md|qmd)$` makes lintr lint the R chunks inside those documents.
DEFAULT_LINT_FILE_PATTERN <- "[.][Rr]$"

is_lint_target <- function(path, pattern = DEFAULT_LINT_FILE_PATTERN) {
  if (!nzchar(pattern)) {
    pattern <- DEFAULT_LINT_FILE_PATTERN
  }
  grepl(pattern, path)
}
