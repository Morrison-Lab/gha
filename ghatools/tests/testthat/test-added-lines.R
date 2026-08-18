test_that("added_lines handles empty and edge case patches", {
  expect_identical(added_lines(NULL), integer(0))
  expect_identical(added_lines(NA_character_), integer(0))
  expect_identical(added_lines(""), integer(0))
})

test_that("added_lines correctly computes added lines with context and deletions", {
  p1 <- paste(
    "@@ -1,3 +1,4 @@",
    " context1",
    "-deleted",
    "+added_at_2",
    "+added_at_3",
    " context4",
    sep = "\n"
  )
  expect_identical(added_lines(p1), c(2L, 3L))
})

test_that("added_lines ignores git-diff headers", {
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
  expect_identical(added_lines(p3), 11L)
})

test_that("added_lines accumulates multiple hunks", {
  p4 <- "@@ -1 +1 @@\n+a1\n@@ -5,2 +5,2 @@\n context\n+b6"
  expect_identical(added_lines(p4), c(1L, 6L))
})

test_that("added_lines handles no newline at end of file marker", {
  p5 <- "@@ -1 +1,2 @@\n keep\n+added2\n\\ No newline at end of file"
  expect_identical(added_lines(p5), 2L)
})
