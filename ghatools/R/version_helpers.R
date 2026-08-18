#' Bump Development Version String
#'
#' Increments the 4th dotted component of a dev version, or appends 9000 to a
#' 3-component release version.
#'
#' @param old Character scalar version string.
#' @return Character scalar with the bumped version.
#' @export
bump_dev_version_string <- function(old) {
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
  paste(parts, collapse = ".")
}

#' Read Version from DESCRIPTION File
#'
#' @param path File path to DESCRIPTION file.
#' @return Character scalar version string.
#' @export
read_version <- function(path) {
  lines <- readLines(path, warn = FALSE)
  idx <- grep("^Version:\\s*", lines)
  if (length(idx) != 1L) {
    stop("Expected exactly one 'Version:' field, found ", length(idx))
  }
  trimws(sub("^Version:\\s*", "", lines[idx]))
}

#' Check if Two Version Strings are Equal
#'
#' @param a First version string.
#' @param b Second version string.
#' @return Logical scalar.
#' @export
versions_equal <- function(a, b) {
  package_version(a) == package_version(b)
}

#' Bump Development Version in DESCRIPTION File
#'
#' @param path File path to DESCRIPTION file.
#' @return List with components `old` and `new`.
#' @export
bump_dev_version <- function(path) {
  lines <- readLines(path, warn = FALSE)
  idx <- grep("^Version:\\s*", lines)
  if (length(idx) != 1L) {
    stop("Expected exactly one 'Version:' field, found ", length(idx))
  }
  old <- trimws(sub("^Version:\\s*", "", lines[idx]))
  new <- bump_dev_version_string(old)
  lines[idx] <- paste0("Version: ", new)
  writeLines(lines, path)
  list(old = old, new = new)
}
