# Pure parsing/enforcement helpers for test-coverage/run-coverage.R.
# Kept free of {covr} so the offline test table can run with base R only.

# covr::package_coverage() type= values. Reject anything else rather than
# forwarding a typo (e.g. "exmaples") that covr would treat as empty work.
.COVR_TYPES <- c("tests", "vignettes", "examples", "all", "none")

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
  bad <- types[!types %in% .COVR_TYPES]
  if (length(bad) > 0L) {
    stop(
      sprintf(
        paste(
          "Invalid coverage type(s) %s;",
          "expected comma-separated values from: %s."
        ),
        paste(bad, collapse = ", "),
        paste(.COVR_TYPES, collapse = ", ")
      ),
      call. = FALSE
    )
  }
  types
}

parse_comment_flag <- function(raw, default = TRUE) {
  raw <- trimws(as.character(raw))
  if (!nzchar(raw)) {
    return(isTRUE(default))
  }
  value <- as.logical(raw)
  if (is.na(value)) {
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
  if (is.na(value) || value < 0 || value > 100) {
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
  if (length(pct) != 1L || !is.finite(pct)) {
    stop(
      sprintf(
        "percent coverage is not a finite number (got %s).",
        paste(deparse(pct), collapse = " ")
      ),
      call. = FALSE
    )
  }
  if (pct < min_pct) {
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
