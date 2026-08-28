# Pure logic for reading, comparing, and bumping an R package's DESCRIPTION
# `Version:` field. Delegates to ghatools version helpers (ghatools/R/version_helpers.R; gha#383).

here <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
file_candidates <- c(
  file.path(here, "..", "..", "ghatools", "R", "version_helpers.R"),
  file.path(here, "..", "..", "..", "ghatools", "R", "version_helpers.R"),
  # Four levels up covers the test suite: source()d from
  # test-description-version.R, `here` is the --file= dir of the TEST file
  # (scripts/tests/), so repo root is one level further than when this
  # script is invoked directly (gha#703).
  file.path(here, "..", "..", "..", "..", "ghatools", "R", "version_helpers.R"),
  "ghatools/R/version_helpers.R"
)
rpkg_file <- file_candidates[file.exists(file_candidates)][1]
if (!is.na(rpkg_file) && file.exists(rpkg_file)) {
  source(rpkg_file)
} else if (requireNamespace("ghatools", quietly = TRUE)) {
  read_version <- ghatools::read_version
  versions_equal <- ghatools::versions_equal
  bump_dev_version_string <- ghatools::bump_dev_version_string
  bump_dev_version <- ghatools::bump_dev_version
} else {
  stop("Unable to locate ghatools package or ghatools/R/version_helpers.R source file")
}


