#' Line numbers a unified diff adds
#'
#' Parse unified-diff text into the new-file line numbers it adds or modifies.
#'
#' Every line type must be handled, not only `+`. A context line advances the
#' new-file counter, a deleted line does not, and a `\ No newline at end of
#' file` marker is not a line at all. Omitting the context branch silently
#' misnumbers every added line after the first context line -- a defect that
#' stays invisible when the diff was produced with `--unified=0`, since that
#' emits no context lines, and appears the moment anyone widens the context.
#'
#' @param diff Character vector of unified-diff lines, or a single string
#'   containing newlines (as the GitHub "list PR files" API returns in its
#'   `patch` field).
#' @returns A named list mapping each new-file path to an integer vector of the
#'   line numbers the diff adds. Empty list for a `NULL`/`NA`/empty input.
#' @examples
#' parse_diff_added(c(
#'   "+++ b/x.qmd", "@@ -1,2 +1,3 @@", " context", "+added", "-gone", "+more"
#' ))
#' @export
parse_diff_added <- function(diff) {
  empty <- is.null(diff) || length(diff) == 0L ||
    (length(diff) == 1L && is.na(diff))
  if (empty) {
    return(list())
  }
  if (length(diff) == 1L) diff <- strsplit(diff, "\n", fixed = TRUE)[[1]]

  out <- list()
  file <- NULL
  newline <- NA_integer_
  for (l in diff) {
    if (grepl("^(diff |index |--- )", l)) {
      # File headers. Present in `git diff`, absent from the API patch field.
      next
    } else if (startsWith(l, "+++ b/") || startsWith(l, "+++ ")) {
      file <- sub("^\\+\\+\\+ (b/)?", "", l)
      if (is.null(out[[file]])) out[[file]] <- integer(0)
    } else if (startsWith(l, "@@")) {
      m <- regmatches(l, regexec("\\+([0-9]+)", l))[[1]]
      newline <- as.integer(m[2])
    } else if (startsWith(l, "+")) {
      if (!is.null(file)) out[[file]] <- c(out[[file]], newline)
      newline <- newline + 1L
    } else if (startsWith(l, "-")) {
      # Deleted: absent from the new file, so the counter does not move.
    } else if (startsWith(l, "\\")) {
      # "\ No newline at end of file": not a real line.
    } else {
      if (!is.na(newline)) newline <- newline + 1L   # context line
    }
  }
  out
}

#' Line numbers a single file's patch adds
#'
#' The single-file form of [parse_diff_added()], matching the shape the GitHub
#' "list PR files" API returns: one `patch` string per file, with no `+++`
#' header to name it.
#'
#' @param patch A single file's unified-diff patch, or `NULL`/`NA` (which the
#'   API returns for binary or too-large files).
#' @returns An integer vector of new-file line numbers, `integer(0)` if none.
#' @export
added_lines <- function(patch) {
  if (is.null(patch) || length(patch) == 0L || all(is.na(patch))) {
    return(integer(0))
  }
  # No `+++` header, so give the parser one to attribute lines to.
  lines <- if (length(patch) == 1L) {
    strsplit(patch, "\n", fixed = TRUE)[[1]]
  } else {
    patch
  }
  res <- parse_diff_added(c("+++ b/<patch>", lines))
  out <- res[["<patch>"]]
  if (is.null(out)) integer(0) else out
}
