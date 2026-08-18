#!/usr/bin/env Rscript

# Offline unit tests for check-ai-tells scanning and extraction logic (gha#382).

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

check <- function(label, condition) {
  if (!condition) {
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

cat("\nAll check-ai-tells tests passed successfully.\n")
