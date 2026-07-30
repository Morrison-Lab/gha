scan_text <- function(lines) scan_lines("t.qmd", lines, seq_along(lines))
n_hits <- function(lines) {
  h <- scan_text(lines)$hits
  if (is.null(h)) 0L else nrow(h)
}
cats <- function(lines) {
  h <- scan_text(lines)$hits
  if (is.null(h)) character(0) else sort(unique(h$category))
}

test_that("every tell category fires on a positive control", {
  expect_true("overused_vocabulary" %in% cats("We delve into the results."))
  expect_true("not_just_antithesis" %in%
                cats("This is not just fast, it's transformative."))
  expect_true("not_only_but" %in%
                cats("It handles not only speed but also accuracy."))
  expect_true("signposting_filler" %in%
                cats("It's worth noting that the model converged."))
  expect_true("hollow_conclusion" %in% cats("In conclusion, the method works."))
  expect_true("promotional" %in% cats("A state-of-the-art approach."))
  expect_true("vague_universal" %in% cats("We tried a variety of settings."))
})

test_that("ordinary technical prose is silent, and does not error", {
  # Not ceremony: an earlier prototype crashed on clean input, so without this
  # the check would have errored on every clean file rather than passing.
  clean <- c(
    "The simulation draws stage transition times from Weibull distributions.",
    "Screening frequency is assigned at baseline and held fixed thereafter.",
    "Bias, RMSE, and coverage are reported for each sample size.",
    "The estimate is robust to the choice of bandwidth."
  )
  res <- scan_text(clean)
  expect_null(res$hits)
  expect_gt(res$words, 20L)
  expect_identical(res$examined, 4L)
})

test_that("code, math, tables, and front matter are excluded", {
  chunk <- c("Prose.", "```{r}", "# delve leverage", "x <- 1", "```")
  expect_identical(n_hits(chunk), 0L)
  expect_identical(n_hits("The `delve` function is unrelated."), 0L)
  expect_identical(n_hits(c("$$", "\\text{delve}", "$$")), 0L)
  expect_identical(n_hits("#| label: delve-example"), 0L)
  expect_identical(n_hits("| delve | leverage |"), 0L)
  expect_identical(n_hits(c("---", "title: delve", "---")), 0L)
})

test_that("a link's visible text is prose but its URL is not", {
  link <- "See [the delve paper](https://example.com/delve)"
  expect_identical(n_hits(link), 1L)
})

test_that("every match on a line is counted, not just the first", {
  # Clustering is the signal the catalog describes, so one-per-line would
  # hide exactly the case worth reporting.
  expect_gte(n_hits("We delve into a seamless, holistic tapestry."), 4L)
})

test_that("word and line counts are reported even when there are no hits", {
  res <- scan_text("A perfectly ordinary sentence about screening intervals.")
  expect_null(res$hits)
  expect_gt(res$words, 5L)
  expect_identical(res$examined, 1L)
})

test_that("a file documenting the tells necessarily contains them", {
  # Not a defect to fix heuristically: the check cannot distinguish prose that
  # exhibits a tell from prose *about* a tell, and should not guess. This test
  # pins the behaviour so the paths-ignore escape hatch stays justified --
  # ai-config's own shared/writing/ai-tells.md, and this file, both trip it.
  documenting <- "The catalog lists delve, leverage, and utilize as overused."
  expect_gte(n_hits(documenting), 3L)
})
