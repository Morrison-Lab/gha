#' Extract Added or Modified Line Numbers from a Unified Diff Patch
#'
#' Parses a single file's unified-diff patch (as returned in the GitHub API
#' `patch` field or from standard `git diff`) and returns the vector of 1-indexed
#' new-file line numbers that were added or modified.
#'
#' @param patch Character scalar containing the patch string, or `NULL`/`NA`.
#' @return Integer vector of new-file line numbers. Returns `integer(0)` if
#'   `patch` is empty, `NULL`, `NA`, or contains no added lines.
#' @export
#' @examples
#' patch <- "@@ -1,3 +1,4 @@\n context\n+new line 2\n context\n+new line 4\n"
#' added_lines(patch)
added_lines <- function(patch) {
  if (is.null(patch) || length(patch) == 0L || is.na(patch)) {
    return(integer(0))
  }
  out <- integer(0)
  new_line <- NA_integer_
  for (line in strsplit(patch, "\n", fixed = TRUE)[[1]]) {
    marker <- substr(line, 1, 1)
    if (grepl("^(diff |index |\\+\\+\\+ |--- )", line)) {
      # File-header lines: present in a full `git diff`, absent from the
      # GitHub API `patch` field. Never a code line -- skip so a "+++ b/file"
      # header is not mistaken for an added line.
      next
    } else if (startsWith(line, "@@")) {
      # Hunk header: @@ -old,n +new,n @@ ; take the new-file start line.
      matched <- regmatches(line, regexec("\\+([0-9]+)", line))[[1]]
      new_line <- as.integer(matched[2])
    } else if (marker == "+") {
      out <- c(out, new_line)
      new_line <- new_line + 1L
    } else if (marker == "-") {
      # Deleted line: absent from the new file, so the counter does not move.
    } else if (marker == "\\") {
      # "\ No newline at end of file": not a real line.
    } else {
      # Context line: present in the new file.
      new_line <- new_line + 1L
    }
  }
  out
}
