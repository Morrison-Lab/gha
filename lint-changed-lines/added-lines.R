# Parse a unified-diff patch into the set of new-file line numbers it adds or
# modifies. Shared by lint-changed-lines.R and its offline tests, so it stays
# free of side effects (no I/O, no global state).

# added_lines(patch): the new-file line numbers a single file's unified-diff
# `patch` (as returned in the GitHub "list PR files" API `patch` field) adds
# or modifies. Returns integer(0) for a NULL/NA/empty patch (binary or
# too-large files, which the API omits a patch for).
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
