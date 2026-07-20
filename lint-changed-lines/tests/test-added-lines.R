#!/usr/bin/env Rscript

# Offline unit tests for added_lines() -- the unified-diff parser that
# lint-changed-lines uses to decide which lines a PR changed. Run with:
#   Rscript lint-changed-lines/tests/test-added-lines.R

# Source added-lines.R whether the test is run from the repo root
# (Rscript lint-changed-lines/tests/test-added-lines.R) or from its own dir.
sourced <- FALSE
candidates <- c(
  "lint-changed-lines/added-lines.R",
  "../added-lines.R",
  "added-lines.R"
)
for (p in candidates) {
  if (file.exists(p)) {
    source(p)
    sourced <- TRUE
    break
  }
}
if (!sourced) stop("could not locate added-lines.R")

check <- function(label, actual, expected) {
  if (!identical(actual, expected)) {
    stop(sprintf(
      "FAIL: %s\n  expected: %s\n  actual:   %s",
      label, paste(expected, collapse = ","), paste(actual, collapse = ",")
    ))
  }
  cat(sprintf("ok - %s\n", label))
}

# Simple hunk: one deletion, two additions, surrounded by context.
p1 <- paste(
  "@@ -1,3 +1,4 @@",
  " context1",
  "-deleted",
  "+added_at_2",
  "+added_at_3",
  " context4",
  sep = "\n"
)
check("simple hunk (additions after a deletion)", added_lines(p1), c(2L, 3L))

# NULL / NA / empty patch (binary or too-large files) -> no lines.
check("NULL patch", added_lines(NULL), integer(0))
check("NA patch", added_lines(NA_character_), integer(0))

# Full git-diff-style patch with file headers, which must be ignored.
p3 <- paste(
  "diff --git a/x.R b/x.R",
  "index 111..222 100644",
  "--- a/x.R",
  "+++ b/x.R",
  "@@ -10,2 +10,3 @@",
  " keep",
  "+newline11",
  " keep2",
  sep = "\n"
)
check("git-diff headers ignored", added_lines(p3), 11L)

# Multiple hunks accumulate across the file.
p4 <- "@@ -1 +1 @@\n+a1\n@@ -5,2 +5,2 @@\n context\n+b6"
check("multiple hunks", added_lines(p4), c(1L, 6L))

# "\ No newline at end of file" is not a real line.
p5 <- "@@ -1 +1,2 @@\n keep\n+added2\n\\ No newline at end of file"
check("no-newline marker ignored", added_lines(p5), 2L)

cat("\nAll added_lines tests passed.\n")
