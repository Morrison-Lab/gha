# Pure parsing/enforcement helpers for test-coverage/run-coverage.R.
# Kept free of {covr} so the offline test table can run with base R only.

parse_coverage_type <- function(raw) {
  raw <- trimws(as.character(raw))
  if (!nzchar(raw)) {
    return("tests")
  }
  types <- trimws(strsplit(raw, ",", fixed = TRUE)[[1]])
  types <- types[nzchar(types)]
  if (length(types) == 0L) {
    return("tests")
  }
  types
}

parse_comment_flag <- function(raw, default = TRUE) {
  raw <- trimws(as.character(raw))
  if (!nzchar(raw)) {
    return(isTRUE(default))
  }
  value <- as.logical(raw)
  if (length(value) != 1L || is.na(value)) {
    stop(
      sprintf(
        "Invalid boolean value %s; expected true or false.",
        raw
      ),
      call. = FALSE
    )
  }
  value
}

parse_min_coverage <- function(raw) {
  raw <- trimws(as.character(raw))
  if (!nzchar(raw)) {
    return(NULL)
  }
  value <- suppressWarnings(as.numeric(raw))
  if (length(value) != 1L || is.na(value) || value < 0 || value > 100) {
    stop(
      sprintf(
        paste(
          "Invalid min-coverage value %s;",
          "expected a number between 0 and 100, or empty to disable."
        ),
        raw
      ),
      call. = FALSE
    )
  }
  value
}

enforce_min_coverage <- function(pct, min_pct) {
  if (is.null(min_pct)) {
    return(invisible(pct))
  }
  if (isTRUE(pct < min_pct)) {
    stop(
      sprintf(
        "Code coverage is %.2f%%, which is below the required %.2f%%",
        pct,
        min_pct
      ),
      call. = FALSE
    )
  }
  invisible(pct)
}
