#!/usr/bin/env Rscript

# Offline unit tests for check-ai-tells scanning, extraction, and diff logic (gha#382).

script_dir <- tryCatch({
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg) > 0) {
    dirname(normalizePath(sub("^--file=", "", file_arg)))
  } else {
    getwd()
  }
}, error = function(e) getwd())

repo_root <- dirname(dirname(script_dir))
check_script <- file.path(repo_root, "check-ai-tells", "check-ai-tells.R")

source(check_script)

check <- function(label, condition, actual = NULL, expected = NULL) {
  if (!condition) {
    if (!is.null(actual)) {
      stop(sprintf("FAIL: %s (actual: %s, expected: %s)", label, deparse(actual), deparse(expected)))
    }
    stop(sprintf("FAIL: %s", label))
  }
  cat(sprintf("ok - %s\n", label))
}

# Test 1: Non-prose stripping
sample_qmd <- c(
  "---",
  "title: Sample",
  "---",
  "Paragraph one with text.",
  "```r",
  "# code with delve",
  "```",
  "Paragraph two with `code span delve` and $math delve$."
)

clean <- strip_non_prose(sample_qmd)
check("YAML header stripped", clean[1] == "" && clean[2] == "" && clean[3] == "")
check("Code block stripped", clean[5] == "" && clean[6] == "" && clean[7] == "")
check("Inline code stripped", !grepl("code span", clean[8]) && !grepl("`", clean[8]))
check("Inline math stripped", !grepl("math delve", clean[8]) && !grepl("\\$", clean[8]))

# Test 2: Negative control produces zero findings
neg_file <- file.path(script_dir, "negative-control.md")
res_neg <- scan_file_prose(neg_file)
check("Negative control has positive word count", res_neg$word_count > 20)
check("Negative control has 0 findings", length(res_neg$findings) == 0L)

# Test 3: Positive control detects lexical and rhetorical tells
pos_file <- file.path(script_dir, "positive-control.md")
res_pos <- scan_file_prose(pos_file)
check("Positive control has findings", length(res_pos$findings) >= 5L)

tells_found <- sapply(res_pos$findings, function(x) x$tell)
check("Found fast-paced", "fast-paced" %in% tells_found)
check("Found testament", "testament" %in% tells_found)
check("Found delve", "delve" %in% tells_found)
check("Found unlock", "unlock" %in% tells_found)
check("Found holistic", "holistic" %in% tells_found)
check("Found elevate", "elevate" %in% tells_found)
check("Found foster", "foster" %in% tells_found)
check("Found landscape", "landscape" %in% tells_found)
check("Found antithesis", "negation-reversal antithesis" %in% tells_found)
check("Found signposting", "signposting filler" %in% tells_found)

# Test 4: Unified diff parsing and multi-line additions
sample_diff <- c(
  "diff --git a/doc.md b/doc.md",
  "index 1234567..89abcdef 100644",
  "--- a/doc.md",
  "+++ b/doc.md",
  "@@ -10,3 +10,5 @@",
  " existing line",
  "+first added line with delve",
  "+second added line with robust",
  " existing end line"
)

diff_map <- parse_git_diff(sample_diff)
check("Diff parsed file name", "doc.md" %in% names(diff_map))
check("Parsed multi-line added lines", identical(diff_map[["doc.md"]], c(11L, 12L)))

# Test 5: Diff-scoped scanning word count and findings scoping
res_diff_scoped <- scan_file_prose(pos_file, added_lines_only = c(3L, 4L))
check("Diff-scoped word count only counts scoped lines", res_diff_scoped$word_count < res_pos$word_count)
check("Diff-scoped only reports tells on scoped lines", all(sapply(res_diff_scoped$findings, function(x) x$line %in% c(3L, 4L))))

# Test 6: Ignore tells parsing and filtering
res_comma <- parse_ignore_tells("robust, landscape")
check("Parse comma-separated ignore-tells", identical(res_comma, c("robust", "landscape")), res_comma, c("robust", "landscape"))

res_rhet <- parse_ignore_tells("robust, negation-reversal antithesis")
check("Parse multi-word rhetorical tell in ignore-tells", identical(res_rhet, c("robust", "negation-reversal antithesis")), res_rhet, c("robust", "negation-reversal antithesis"))

res_space <- parse_ignore_tells("robust landscape")
check("Parse space-separated ignore-tells", identical(res_space, c("robust", "landscape")), res_space, c("robust", "landscape"))

res_single_mw <- parse_ignore_tells("signposting filler")
check("Parse single multi-word tell without comma", identical(res_single_mw, c("signposting filler")), res_single_mw, c("signposting filler"))

res_empty <- parse_ignore_tells("")
check("Parse empty ignore-tells", length(res_empty) == 0L, length(res_empty), 0L)

ignored_set <- parse_ignore_tells("delve, elevate, signposting filler")
filtered_pos <- Filter(function(x) !(tolower(x$tell) %in% ignored_set), res_pos$findings)
tells_filtered <- sapply(filtered_pos, function(x) x$tell)
check("Ignored delve suppressed", !("delve" %in% tells_filtered), "delve" %in% tells_filtered, FALSE)
check("Ignored elevate suppressed", !("elevate" %in% tells_filtered), "elevate" %in% tells_filtered, FALSE)
check("Ignored signposting filler suppressed", !("signposting filler" %in% tells_filtered), "signposting filler" %in% tells_filtered, FALSE)
check("Unignored holistic remains", "holistic" %in% tells_filtered, "holistic" %in% tells_filtered, TRUE)

cat("\nAll check-ai-tells tests passed successfully.\n")
