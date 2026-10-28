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

sourced <- FALSE
candidates <- c(
  ".github/workflows/scripts/tests/r-test-helpers.R",
  "../.github/workflows/scripts/tests/r-test-helpers.R",
  "../../.github/workflows/scripts/tests/r-test-helpers.R"
)
for (p in candidates) {
  if (file.exists(p)) {
    source(p)
    sourced <- TRUE
    break
  }
}
if (!sourced) stop("could not locate r-test-helpers.R")

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

# is_lint_target(): which changed files get linted.
qmd_pattern <- "[.]([Rr]|[Rr]md|[Qq]md)$"

# The default pattern keeps the historical behaviour: R source files only.
check("default matches .R", is_lint_target("R/a.R"), TRUE)
check("default matches .r", is_lint_target("R/a.r"), TRUE)
check("default skips .qmd", is_lint_target("chapters/a.qmd"), FALSE)
check("default skips .Rmd", is_lint_target("a.Rmd"), FALSE)

# An empty pattern falls back to the default rather than matching everything.
check("empty pattern is the default (R)", is_lint_target("a.R", ""), TRUE)
check("empty pattern is the default (qmd)", is_lint_target("a.qmd", ""), FALSE)

# A document pattern adds Quarto and R Markdown but still anchors the extension.
check("document pattern matches .qmd", is_lint_target("a.qmd", qmd_pattern), TRUE)
check("document pattern matches .Qmd", is_lint_target("a.Qmd", qmd_pattern), TRUE)
check("document pattern matches .Rmd", is_lint_target("a.Rmd", qmd_pattern), TRUE)
check("document pattern matches .R", is_lint_target("a.R", qmd_pattern), TRUE)
check("document pattern skips .md", is_lint_target("a.md", qmd_pattern), FALSE)
check("document pattern skips .qmd.bak", is_lint_target("a.qmd.bak", qmd_pattern), FALSE)

cat("\nAll added_lines and is_lint_target tests passed.\n")
