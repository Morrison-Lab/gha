# Parse a unified-diff patch into the set of new-file line numbers it adds or
# modifies. Delegates to ghatools::added_lines (ghatools/R/added_lines.R; gha#383).

here <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
file_candidates <- c(
  file.path(here, "..", "ghatools", "R", "added_lines.R"),
  file.path(here, "..", "..", "ghatools", "R", "added_lines.R"),
  "ghatools/R/added_lines.R"
)
rpkg_file <- file_candidates[file.exists(file_candidates)][[1]]
if (!is.na(rpkg_file) && file.exists(rpkg_file)) {
  source(rpkg_file)
} else if (requireNamespace("ghatools", quietly = TRUE)) {
  added_lines <- ghatools::added_lines
} else {
  stop("Unable to locate ghatools package or ghatools/R/added_lines.R source file")
}


