# Pure logic for reading, comparing, and bumping an R package's DESCRIPTION
# `Version:` field. Shared by bump-dev-version.yml (increments the dev-version
# counter after a merge to main) and version-check.yml (asserts a PR did NOT
# touch the Version: line -- see those workflows' own comments for why).
#
# Deliberately depends on nothing but base R's `package_version` class rather
# than the `desc` package: `desc` needs `install.packages()` (a slow, network-
# dependent CI step) for parsing/comparison base R already does natively.
# No I/O beyond the two functions that need it (read_version_line/
# bump_dev_version), so the rest stays free of side effects for testing.

# Index of the (exactly one expected) "Version:" line in a DESCRIPTION file's
# lines. Errors if there isn't exactly one -- a missing or duplicated Version:
# field means something is already wrong with the file.
version_line_index <- function(lines) {
  idx <- grep("^Version:\\s*", lines)
  if (length(idx) != 1L) {
    stop("Expected exactly one 'Version:' field, found ", length(idx))
  }
  idx
}

# read_version(path): the DESCRIPTION Version: field at `path`, as a string.
read_version <- function(path) {
  lines <- readLines(path, warn = FALSE)
  idx <- version_line_index(lines)
  trimws(sub("^Version:\\s*", "", lines[idx]))
}

# versions_equal(a, b): TRUE if two DESCRIPTION-style version strings name the
# same version. Uses package_version's own equality, which treats a missing
# trailing component as zero (e.g. "0.1.0" == "0.1.0.0") -- the same rule R's
# own dependency-version matching uses, so this doesn't invent a comparison
# rule of its own.
versions_equal <- function(a, b) {
  package_version(a) == package_version(b)
}

# bump_dev_version(path): increments the development-version counter (the 4th
# dotted component, e.g. 0.1.0.9057 -> 0.1.0.9058) in the DESCRIPTION at
# `path`, and writes the result back. A version with exactly 3 components (a
# release just cut, e.g. 0.1.0) starts a new dev cycle at .9000, per the lab
# manual's "Development versions: 0.0.0.9000, 0.0.0.9001, ..." convention.
# Returns list(old = <old version string>, new = <new version string>).
bump_dev_version <- function(path) {
  lines <- readLines(path, warn = FALSE)
  idx <- version_line_index(lines)
  old <- trimws(sub("^Version:\\s*", "", lines[idx]))
  parts <- unclass(package_version(old))[[1]]
  if (length(parts) == 4L) {
    parts[4] <- parts[4] + 1L
  } else if (length(parts) == 3L) {
    parts <- c(parts, 9000L)
  } else {
    stop(
      "Version '", old, "' has ", length(parts),
      " components; expected 3 (a release) or 4 (a dev version)"
    )
  }
  new <- paste(parts, collapse = ".")
  lines[idx] <- paste0("Version: ", new)
  writeLines(lines, path)
  list(old = old, new = new)
}
