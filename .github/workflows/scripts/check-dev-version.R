#!/usr/bin/env Rscript

# Fail if a PR's DESCRIPTION Version: differs from the base branch's.
#
# Inverts the old RMI-PACTA-derived "branch version must exceed main's" rule:
# now that bump-dev-version.yml owns the dev-version bump after every merge to
# main, a PR is never supposed to touch the Version: line at all -- doing so
# just guarantees a collision with the next PR that merges. See
# check-dev-version's own calling workflow (version-check.yml) for the label
# and bump-branch bypasses (a genuine release-cut PR, and the bump PR itself).
#
# Usage: Rscript check-dev-version.R <working-DESCRIPTION> <compare-DESCRIPTION>
# Exits 1 (with a message) if the versions differ; 0 if they match.

here <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)))
source(file.path(here, "description-version.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) {
  stop("Usage: Rscript check-dev-version.R <working-DESCRIPTION> <compare-DESCRIPTION>")
}

working_version <- read_version(args[[1]])
compare_version <- read_version(args[[2]])
message("PR branch version:   ", working_version)
message("Base branch version: ", compare_version)

if (!versions_equal(working_version, compare_version)) {
  message(
    "DESCRIPTION's Version: field differs from the base branch. ",
    "The dev version is bumped automatically after this PR merges -- ",
    "revert your own change to it (or apply the 'no version increment' ",
    "label if this genuinely is a release-cut PR)."
  )
  quit(status = 1)
}
message("Version unchanged -- all set!")
