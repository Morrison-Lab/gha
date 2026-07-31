#!/usr/bin/env Rscript

# Bump a DESCRIPTION file's dev-version counter and write the result back.
# Called by bump-dev-version.yml after a merge to main, so PRs never need to
# touch the Version: line themselves (see version-check.yml, which now fails
# a PR that DOES change it).
#
# Usage: Rscript bump-dev-version.R <path-to-DESCRIPTION>
# Prints "old_version=X" and "new_version=Y" lines, suitable for appending
# straight to $GITHUB_OUTPUT.

here <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(here, "description-version.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) {
  stop("Usage: Rscript bump-dev-version.R <path-to-DESCRIPTION>")
}

result <- bump_dev_version(args[[1]])
cat("old_version=", result$old, "\n", sep = "")
cat("new_version=", result$new, "\n", sep = "")
