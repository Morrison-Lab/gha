test_that("context lines advance the new-file counter", {
  # The bug this exists to prevent: omitting the context branch misnumbers
  # every added line after the first context line. Invisible under
  # --unified=0, which emits no context, and wrong the moment anyone widens it.
  got <- parse_diff_added(c(
    "diff --git a/x.qmd b/x.qmd", "--- a/x.qmd", "+++ b/x.qmd",
    "@@ -1,2 +1,3 @@", " context line", "+added one", "-removed", "+added two"
  ))
  expect_identical(names(got), "x.qmd")
  expect_identical(got[["x.qmd"]], c(2L, 3L))
})

test_that("deleted lines do not advance the counter", {
  got <- parse_diff_added(c("+++ b/y.qmd", "@@ -1,3 +1,2 @@", "-gone", "+kept"))
  expect_identical(got[["y.qmd"]], 1L)
})

test_that("a no-newline marker is not a line", {
  got <- parse_diff_added(c(
    "+++ b/z.qmd", "@@ -1 +1,2 @@", "+one", "\\ No newline at end of file", "+two"
  ))
  expect_identical(got[["z.qmd"]], c(1L, 2L))
})

test_that("multiple files are attributed separately", {
  got <- parse_diff_added(c(
    "+++ b/a.qmd", "@@ -0,0 +1 @@", "+alpha",
    "+++ b/b.qmd", "@@ -0,0 +5 @@", "+beta"
  ))
  expect_identical(got[["a.qmd"]], 1L)
  expect_identical(got[["b.qmd"]], 5L)
})

test_that("empty and missing input yield empty results", {
  expect_identical(parse_diff_added(NULL), list())
  expect_identical(parse_diff_added(NA), list())
  expect_identical(added_lines(NULL), integer(0))
  expect_identical(added_lines(NA_character_), integer(0))
})

test_that("added_lines() handles a single-file API patch with no header", {
  expect_identical(
    added_lines("@@ -1,2 +1,3 @@\n context\n+one\n-gone\n+two"),
    c(2L, 3L)
  )
})
